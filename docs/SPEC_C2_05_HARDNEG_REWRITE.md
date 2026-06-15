# C2-05 实现规格：hard-negative 重写 + 检索复验

交给：Codex。出规格：Claude（已核 `check_eval_leakage.py`、`hard_negative_eval.jsonl`、
`HARD_NEGATIVE_ADJUDICATION.md §4`）。对应：ROADMAP C2-05。
解锁：Phase 3 动作 c（version-scoped retrieval）的去留决策；hard-negative 的**第一个有效**
检索测量；（可选）真实 wrong_side 锚点。

------

## 0. 背景（一句话）

Week 6 的 hard_negative split 全灭（doc_hit@5=0.05，error=1.0）已被裁定为 **F8（出题缺陷）**：
20 条 query 是无内容词的元数据模板（"answer from side A of group X"），检索无从下手。
本任务用含内容词的公平 query 重测，看 **F3（真实检索弱点）是否存在**。

## 1. 前置（Owner，阻塞）

Owner 逐条确认 `HARD_NEGATIVE_ADJUDICATION.md §4` 表里的 **18 条替换 query 草稿**
（cases 001–018），可改写。**019/020 弃用**（gold 是 HTML/元描述样板，§4 已标），
split 收缩为 **n=18**。这是 eval-author 环节；Owner 签字 + 下面的泄漏检查是隔离保障
（query 由 Claude 起草时看过 reference answer，须靠 answer-copy 检查兜底）。

## 2. Codex 步骤

### a. 重写 `data/gold_eval/hard_negative_eval.jsonl`

- cases 001–018：`query` 换成 Owner 确认的 §4 文本（含 §4b 的 002/005/007/016 修正）。
  **gold_doc_ids / gold_chunk_ids / hard_negative_group_id / reference_answer /
  expected_behavior 全部不变**——答案侧没变，只换问法。
  `query_source="manual_adversarial_rewrite"`，`query_style="standard"`，
  `title_overlap_score` 清空（由泄漏检查回填）。
- 删除 019、020 两行。新文件 **18 行**。eval jsonl **保持评分专用**（query + gold），
  不加诊断字段。

### a2. 诊断标注（独立文件，**非评分**）

写 `data/gold_eval/hard_negative_rewritten_v1_annotations.jsonl`，按 case_id 关联，
每条含（来源：外部分析采纳项）：

```json
{"case_id":"hard-negative-001","difficulty_tier":"A",
 "gold_distinguishers":["example payloads","request body","generated API docs"],
 "anti_should_not_satisfy_because":"Extra Data Types covers additional Python/Pydantic types, not documenting request-body example payloads.",
 "expected_answer_focus":"declaring request-body examples that surface in API docs",
 "failure_mode_targeted":"wrong_side_retrieval"}
```

**硬护栏**：这些字段是**人工审计指引 + trajectory 归因素材**，
- 不进 query、不进 retrieval 打分路径；
- **绝不**自动当 pass/fail（避免再造一个未验证的 rule-based judge——judge harness 已
  证明这类自动判定会出错）；
- `difficulty_tier` 是 pre-run 预测，复跑后据 doc_hit@5 复核，报告不得当测量值。
- 不改 `EvalCase` schema（保持评分 schema 稳定；annotations 是旁路文件）。

### b. 扩展 `scripts/check_eval_leakage.py` 为**双向边界**（ADJUDICATION §6 教训）

现状只有上限（`title_overlap > 0.6` → high_title_overlap）。新增：

- **下限（新，关键）**：query 与**其 gold chunk 正文**的内容词重合必须 > 0。
  重合≈0 → flag `no_retrievable_content`。这一条专抓"零内容元数据题"——
  正是 Week 6 漏掉的方向（泄漏检查只防信息过多，没防信息为零）。
- **hard_negative 例外**：similar_title 对的区分词本身就是标题词，故对 hard_negative split
  **不因 high_title_overlap 自动判失败**（只报告）；该 split 的 gating flag 用下限 +
  answer-copy。
- 保留 answer-copy 检查（`copy_score > 0.8` 拒绝）——这是 Claude 看过答案后的兜底。

### c. 跑泄漏检查并归档

对重写 split 跑 `check_eval_leakage.py`，归档报告。任何 case 触发 `no_retrievable_content`
或 answer-copy → 改写措辞，直到 18 条全过。

### d. 校验 gold

确认 18 条的 `gold_chunk_ids` 仍指向当前索引里真实存在的 chunk（gold 未变，但要确认 id
未因重建漂移）。漂移则回填。

### e. 检索复跑（**零 LLM token**）

```bash
python scripts/run_eval.py --split hard_negative \
  --systems vector_only,bm25_only,hybrid_rrf,hybrid_rrf_rerank --retrieval-only \
  --run-id q2-c205-hardneg-rewritten-retrieval
```
输出 doc_hit@5 / hit@5 / mrr / hard_negative_error_rate，与坏基线 0.05 / 1.0 对比。

## 3. 解读（决定动作 c）

| 复跑结果 | 结论 | Phase 3 动作 c |
| --- | --- | --- |
| doc_hit@5 显著回升（如 ≥0.5） | **F8 确认**：原测试不公平；检索层无 F3 | 动作 c 理据弱，可砍/缓 |
| doc_hit@5 仍低 | **F3 为真**：检索确实分不开相似对 | 动作 c 成立，保留 |

**诚实红线**：
- 回升 **≠ 鲁棒性证明**。它只说明原测试是坏的；重写 split 是**全新的公平测试**，
  报告它的数字为"hard-negative 检索的首个有效测量"，不得说成"相对 Week 6 的提升"
  （Week 6 那次无效，不可比）。
- n=18，按此报告。

## 4. 可选（later，≈18 LLM calls）

对重写 split 跑一次 real run（final_agentic）→ 产出 answer + citation，可供人工/judge
审 wrong_side，**补上 judge harness 当前缺的真实 wrong_side 锚点**（见
`JUDGE_AGREEMENT_REPORT.md`：probe-only 验证 wrong_side 是当前局限）。
默认不做，需要时再排；做的话产物按 grounded 口径，不进 headline。

## 5. 验收

```text
1. hard_negative_eval.jsonl = 18 行，query 重写，gold 不变且可解析。
2. check_eval_leakage.py 双向边界生效；新增下限单测；报告归档；18 条全过下限+answer-copy。
3. q2-c205-hardneg-rewritten-retrieval 落盘；doc_hit@5/error 报告并对比 0.05/1.0。
4. FAILURE_ANALYSIS.md F3/F8 按复跑结论更新；EVALUATION_REPORT hard-negative 节更新
   (n=18, 重写, 公平测量值)。
5. ruff + tests 绿；核心步骤(e) 零 LLM token。
```

## 6. 不做

```text
- 不改 gold 语义（只换 query 措辞）；不动 fixture/external/obfuscated split。
- 不把回升包装成鲁棒性；不与 Week 6 做"改进"对比。
- real run（§4）默认不跑，不在本任务消耗 token。
```
