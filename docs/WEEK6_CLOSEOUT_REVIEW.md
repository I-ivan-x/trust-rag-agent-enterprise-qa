# Week 6 Closeout 审查存档

> 审查者：Claude（非代码执行者，只读审查）
> 审查对象：Week 6 closeout patch（补齐上一轮指出的 Week 6 缺口，未重跑 full real LLM，未消耗 DeepSeek token）
> 审查方式：只读命令 + 报告精读；全部 12 个 `summary.json` 经 Bash python 严格 JSON 校验通过；ruff 通过；公共索引状态实测。

## 1. 总体结论：pass（可提交 Week 6）

上一轮指出的全部缺口均已补齐，补齐方式诚实、边界干净、未消耗 token、未越界 Week 7/8。无 blocking 问题。

## 2. 缺口补齐核对

| 缺口 | 状态 | 证据 |
| --- | --- | --- |
| external retrieval-tier 消融 | 已补齐 | run `week6-external-retrieval-ablation`，4 系统，retrieval_only，50/50 |
| fixture 36 条功能回归 | 已补齐 | run `week6-fixture-functional-regression`，36/36，mock_smoke |
| EVALUATION_REPORT 污染专章 | 已补 | "Contamination / Parametric Leakage Analysis" 节 |
| false_refusal / false_answer trade-off | 已补 | "False Refusal / False Answer Trade-off" 节 |
| FAILURE_ANALYSIS taxonomy | 已补 | 升级为 F1–F8 完整失败分类 |
| hard_negative_error_rate=1.0 根因 | 已补 | F3 + F8 + 专节，含真实 trace 证据 |
| CITATION_AUDIT rule-based ≠ 人工 caveat | 已补 | "Manual Citation Support Audit Status" 节 |
| WEEK6_CLOSEOUT_REVIEW_PACKET | 已生成 | 含完整 run inventory 与全部章节 |

## 3. Retrieval-tier 消融审查

- 系统：vector_only / bm25_only / hybrid_rrf / hybrid_rrf_rerank 四系统全跑。
- 真实栈：`uses_real_embedding=true`、`uses_real_reranker=true`、`toy_retrieval=false`、`llm_call_count=0`、`mock_used=false`，零 token。

| system | hit@5 | doc_hit@5 | gold_doc_recall@5 | mrr |
| --- | ---: | ---: | ---: | ---: |
| vector_only | 0.12 | 0.60 | 0.59 | 0.4967 |
| bm25_only | 0.28 | 0.80 | 0.77 | 0.6547 |
| hybrid_rrf | 0.28 | 0.80 | 0.79 | 0.6400 |
| hybrid_rrf_rerank | 0.18 | 0.78 | 0.76 | 0.6113 |

- **rerank 提升未被证明**：hybrid_rrf_rerank 在 hit@5 / doc_hit@5 / recall / mrr 上均略低于 hybrid_rrf；报告明确写 "No rerank improvement may be claimed from this run"。
- 可声称：BM25/hybrid 在该 split 上显著优于 vector-only（doc_hit@5 0.80 vs 0.60）；retrieval metrics ≠ answer accuracy（报告已注明）。
- 不可声称：reranker 改善检索。

## 4. Fixture 回归审查

- 36/36，systems final_gated + final_agentic，mock_smoke，`headline_eligible=false`，`headline_scope=smoke`，`mock_used=true`，`toy_retrieval=true`，`llm_call_count=0`，`expected_rewrite_used=false`。
- response-mode 覆盖 no_evidence / permission_denied / deprecated_only / conflict_detected。
- 足以确认功能回归未坏，明确不进 headline，零 token。

## 5. 报告诚实性审查

四份文档全部诚实、无简历话术、无夸大数字：

- EVALUATION_REPORT：grounded 为 headline、raw 仅作污染信号、direct_llm grounded=0、rerank not proven、agentic tie、hard-negative failure、over-refusal trade-off 全部明写。
- FAILURE_ANALYSIS：F1–F8 taxonomy，每条含 definition / evidence / root-cause / impact / mitigation；hard-negative 根因用真实 trace（0019/0020 组挤占 0001/0002 gold）佐证。
- CITATION_AUDIT：明确 rule-based v1 ≠ 人工审计，citation_valid=1.0 为结构有效而非人工支持，禁止 "citation accuracy X%" 话术。
- WEEK6_CLOSEOUT_REVIEW_PACKET：safe / unsafe-to-cite 清单 + remaining blockers 齐全，适合作为 Week 6 收口审查材料。

## 6. Hard-negative 失败审查

诚实达标：承认 real stress-test failure、未包装成 robust、指出 retrieval/rerank confusion、明确"现有证据无法完全区分检索失败与 hard-negative gold/pair 设计问题"，并给出合理 mitigation（更强 reranker、metadata-aware rerank、人工 adjudication）。F8 专列 "Gold Definition / Evaluation Mismatch Risk"。

## 7. Citation audit 状态

当前为 rule-based v1，非人工审计；不能写 citation accuracy X%；Q1 closeout 仍需 ≥25（理想 40）条人工 citation-support 审计 + 一周后复标自一致率。CITATION_AUDIT 与 packet 声明一致。

## 8. 可写 / 不可写结论

- 可写（resume-safe）：可信 RAG-Agent，覆盖 grounded scoring / gates / citation binding / 真实 DeepSeek 评测；低 false-answer，并诚实记录 over-refusal 与 hard-negative 失败。
- 不可写（resume-unsafe）：agentic 提升性能；hard-negative robust；无人工审计的 citation accuracy；reranker 改善检索；raw correctness 当系统质量。

## 9. 产物与索引卫生

- 公共索引已恢复：`index_metadata.json` → chunks_path=`data/generated/public/chunks.jsonl`，chunk_count / vector_count / keyword_count = 442，built_at 晚于所有 run，证明 hard-negative 临时索引已回滚。
- `.env`、`docs/Q1_HARD_DEMO_TASK_PLAN.md` 未改。
- `data/eval_runs/*` 被 gitignore，不进 git diff。
- 无 DeepSeek token 消耗（ablation / fixture 均 llm_call_count=0）。
- 全部 12 个 summary.json 严格 JSON 校验通过（含 fixture / ablation）；此前疑似 trailing comma 为终端渲染伪影，文件本身有效。
- ruff 通过；本轮 git diff 与上轮一致（未新增 app 代码改动，符合"只补 docs + run"）。

## 10. Out-of-scope 检查

未进入 Week 7/8：无 Dockerfile / compose / Makefile / smoke_test / Streamlit / deployment / slides / resume wording / demo video。

## 11. Blocking issues

无。

## 12. Non-blocking notes

1. EVALUATION_REPORT headline 表未列 hard_negative 的 retrieval-only 行（仅列 final_agentic），可在 Week 8 补 hybrid_rrf_rerank=0.05 一行；不影响诚实度（ablation/packet 已含）。
2. fixture mock grounded=0.3889 为 toy/mock 数字，报告已标 headline_eligible=false，建议在表格旁再加一句"非真实质量"以防被误引。
3. 非本轮项：`app/generation/llm_client.py` 遗留模块（若仍在）建议清理。
4. `docs/WEEK6_CLOSEOUT_REVIEW_PACKET.md` 为新增 untracked 文件，commit 时记得纳入。

## 13. Codex 修复项

No blocking fixes required before Week 6 commit.

（第 12 节均为 Week 7/8 顺手项，不阻塞。）

## 14. 提交判定

可以 commit。

建议 commit message：

```
eval: week 6 closeout — external retrieval ablation, fixture regression, honest taxonomy and contamination report
```

## 15. Q1 收尾剩余 blocker（提交后跟踪）

- 必做才能算 Q1 完成：人工 citation-support audit（≥25 条，理想 40 条）+ 一周后复标。
- Week 7/8 交付（不阻塞 Week 6）：Docker / docker-compose / Makefile / smoke_test、README 终版、TECHNICAL_DESIGN、DEMO_SCRIPT、INTERVIEW_QA、RESUME_BULLETS、release tag `v0.3-q1-hard-demo`。
