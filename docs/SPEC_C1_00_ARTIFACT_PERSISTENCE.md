# C1-00 实现规格：审计前置——持久化 answer/claims/citations

交给：Codex（单代码执行者）。出规格：Claude（已读 runner.py / real_pipeline.py /
citation_binder.py / answer_generator.py / citation.py 确认）。
对应：ROADMAP C1-00。解锁：CITATION_AUDIT_GUIDE.md §0 的审计 artifact gap。

------

## 0. 前置：先修环境

当前环境缺依赖，`pytest` 直接挂在 `ModuleNotFoundError: No module named
'pydantic_settings'`。动手前先 `uv sync`，跑通 `pytest tests/unit` 确认绿
baseline，再改代码。

## 1. 问题定位（已读码确认）

审计单元是 (claim, cited chunk set)。这三样数据在 real run 时**全部存在但被丢弃**，
缺口在**两层**，不是一层：

- **real_pipeline 层（根因）**：`run_real_final_pipeline` 在
  `app/eval/real_pipeline.py:145-147` 调 `bind_citations` 得到 `bound`，
  其中 `bound.claims`（`list[BoundClaim]`，每条带 `text` /
  `supporting_chunk_ids` / `citation_ids`）**就是审计需要的 claim→引用映射**，
  但函数只取了 `bound.answer_text` 和 `bound.citations`，`bound.claims` 当场丢弃，
  从未进入 `RealFinalResult`。
- **runner 层**：`_run_case_real`（`app/eval/runner.py:310`）拿 `real.answer_text` /
  `real.citations` 去算分（runner.py:337-341、447），算完即弃；写盘的
  `results.jsonl` 行由 `EvalResult.model_dump()` 生成，schema 不含任何答案内容。

结论：必须先让 `RealFinalResult` 携带 claims，再让 runner 落盘。

## 2. 改动清单

### 2.1 `app/eval/real_pipeline.py`

1. `RealFinalResult` dataclass 新增字段：
   ```python
   claims: list[BoundClaim] = field(default_factory=list)
   ```
   import：`from app.answer.citation_binder import BoundClaim`。
2. `run_real_final_pipeline` 的 answer 分支（real_pipeline.py:145-149）：
   `bound = bind_citations(...)` 之后，把 `bound.claims` 传入 `RealFinalResult(...)`
   的 `claims=bound.claims`（refusal 分支保持 `claims=[]`，即 default）。
3. `run_direct_llm_baseline` 的两个 `RealFinalResult(...)`：`claims=[]`（direct_llm
   无检索无引用，保持空——这也是审计排除 direct_llm 的代码层依据）。

### 2.2 `app/eval/runner.py` — 新增 `answers.jsonl` 产物

**设计选择**：不动 `EvalResult` schema（大量测试依赖它），改为新增独立产物
`answers.jsonl`。理由：审计只需已答 case 的内容；独立文件隔离变更面，schema 稳定。

1. `_run_case_real` 的返回 dict 增加键 `"answer"`，值为一个 answer 行 dict（§3 schema）。
   构造时：
   - claims 来自 `real.claims`（逐条 `model_dump(mode="json")`）；
   - citations 来自 `real.citations`（逐条 `model_dump(mode="json")`）；
   - **被引 chunk 正文快照**：对出现在 `real.citations` 里的每个 `chunk_id`，
     在 `real.reranked_chunks` 中按 `item.chunk.chunk_id` 查 `item.chunk.text`，
     写入 `cited_chunk_texts: {chunk_id: text}` 与
     `cited_text_sha256: {chunk_id: sha256(text)}`。
     查不到的 chunk_id：text 记 `null`、sha256 记 `null`，并在行内
     `warnings` 追加 `"cited_chunk_not_in_reranked:{chunk_id}"`——**禁止静默丢弃**，
     快照必须诚实反映缺失。
   - 验证点：确认 `RetrievedChunk.chunk` 有 `.text` 字段（prompt 构造在
     answer_generator.py:121 用过 `chunk.text`，但那是 ContextChunk；
     reranked_chunks 是 RetrievedChunk，需确认其 `.chunk` 同样暴露 text，
     否则改为从 context 链路取）。
2. `_run_case_offline` 的返回 dict 也加 `"answer": None`（保持键一致，mock 行不写）。
3. `run_eval` 主循环（runner.py:85-113）：收集 `row["answer"]`，非 None 的进
   `answer_rows`。
4. 落盘（runner.py:134 附近）：
   ```python
   write_jsonl(run_dir / "answers.jsonl", answer_rows)
   ```
   仅 real run 会有非空 `answer_rows`；retrieval-only / mock 为空文件或不写
   （二选一，与现有 write_jsonl 对空列表的行为保持一致即可）。

## 3. `answers.jsonl` 行 Schema

```json
{
  "run_id": "string",
  "case_id": "external-012",
  "system_name": "final_agentic",
  "eval_split": "external",
  "refused": false,
  "response_mode": "answer",
  "answer_text": "...",
  "llm_model_name": "deepseek-v4-flash",
  "claims": [
    {"claim_id": "claim-0001", "text": "...",
     "supporting_chunk_ids": ["..."], "citation_ids": ["CIT-0001"]}
  ],
  "citations": [
    {"citation_id": "CIT-0001", "doc_id": "...", "chunk_id": "...",
     "section_path": ["..."], "locator": {...}}
  ],
  "cited_chunk_texts": {"<chunk_id>": "<frozen text or null>"},
  "cited_text_sha256": {"<chunk_id>": "<hex or null>"},
  "warnings": []
}
```

refused case：`answer_text` 为拒答文案、`claims`/`citations`/`cited_*` 为空——
仍写行（审计要据此知道哪些 case 因拒答无可审 claim）。

## 4. 复跑（解锁 7 天复标时钟）

补丁通过测试后，复跑（**仅 external + obfuscated**；hard_negative 是模板 query，
推迟到 Q2-W1 重写后，见 CITATION_AUDIT_GUIDE.md §0）：

```bash
python scripts/run_eval.py --split external   --systems final_agentic --real-run \
    --run-id week7-audit-external-final-agentic
python scripts/run_eval.py --split obfuscated --systems final_agentic --real-run \
    --run-id week7-audit-obfuscated-final-agentic
```

约 65 次 LLM 调用，≈¥5。real LLM smoke（Codex 清单第 2 项）并入这次，不单跑。
审计引用这两个新 run_id，**不得宣称审计了原始 Week 6 run**（答案重新生成，
非确定性差异是预期，报告声明一次）。

## 5. 验收标准

```text
1. uv sync 后 pytest tests/unit 全绿（baseline）。
2. RealFinalResult.claims 在 answer 分支非空、refusal/direct_llm 分支为空——加单测。
3. 新增 answers.jsonl 行 schema 测试（test_answers_artifact.py）：
   - answered final_agentic case：claims 非空，每个 supporting_chunk_id 都能在
     cited_chunk_texts 找到非 null 文本（或带 warning）；
   - refused case：写行且 claims/citations 为空；
   - sha256 与 text 一致。
4. 复跑两个 run 落盘 answers.jsonl，行数 = case 数 × 1 系统。
5. 已答 case 的 claim 总数 ≥ 13（external 已答约 13 case，足够支撑 25 条审计样本）。
6. ruff check 通过；EvalResult schema 未改（现有测试不回归）。
```

## 6. 不做（范围边界）

```text
不改 EvalResult schema；不改 trace schema（answers.jsonl 是独立产物）；
不改 hard_negative（推迟到 C2-05/Q2-W1）；不接 OTel；
不动 citation 评分逻辑（只持久化，不改指标）。
```
