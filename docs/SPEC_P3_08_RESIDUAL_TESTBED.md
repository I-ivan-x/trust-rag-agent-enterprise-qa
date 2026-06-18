# P3-08 实现规格：Agent 残余场景测试床（`agent_residual_v1`）

交给：Codex（wiring + 验证 gate + 泄漏检查）。语料/query 草稿由 Claude 提供（§5）。
设计：`Q2_AGENT_DESIGN.md` §3.1 / §7 / §8。前置：P3-01~06 已落地。

## 0. 目标（为什么这是消融的前提）

决议 A（rule vs llm controller）只有在**控制器的"选择"真有内容**时才有信息量。
当诊断只给一个合法恢复动作时，两控制器必选一样 → 消融平局、无意义。
所以测试床**必须含 ≥6 条 a/b 共现 case**（legal_actions == {a,b,e}），让 rule（按 b>a 选 b）
和 llm（可能选 a）有机会分叉。这是本任务的硬指标。

**范围**：构造 split + 语料 + 验证 gate + 泄漏检查 + gold 回填。
**不做**：跑真实 eval（P3-09）、pass^k（P3-10）、replay（TF1）。验证 gate 用 diagnose() 零 token。

## 1. split 组成（~10 条）

| 类型 | 条数 | 预期 legal_actions | 触发信号 |
| --- | --- | --- | --- |
| 共现（a+b 决策点） | **≥6** | {a, b, e} | weak_recall **且** policy_crowding 同时 |
| 纯 weak_recall（动作 a） | 2 | {a, e} | 仅 query 弱召回（缩写/口语，entity_miss） |
| 纯 policy_crowding（动作 b） | 1 | {b, e} | 仅 deprecated/restricted 邻居挤占 |
| no_recovery 或 conflict | 1 | {e} 或 {d, e} | 兜底分支 |

## 2. 语料结构（控制信号可靠触发）

新建受控小语料 `data/agent_residual_corpus/`（`corpus_source=agent_residual`，
默认不进 headline 索引，开关同 redteam）。每条**共现 case** 一个 topic：

```text
1 个 gold 文档：status=active，含正确答案（clean evidence）
2 个 sibling 文档：同 topic，status=deprecated 或 access=restricted
query：缩写/口语/术语错位，使 gold 实体不被直接命中（entity_miss）
```

检索这条 query → 拉到 gold(active) + 2 个 deprecated/restricted 邻居，且 gold 被挤到
clean_active < min_support → **同时**触发 weak_recall + policy_crowding → legal={a,b,e}。
纯 a / 纯 b case 去掉对应另一半结构。

**阈值依赖（重要）**：诊断信号阈值（min_support / min_score / 邻居计数）目前是
`diagnosis.py` 的 TODO-W7 占位值。**测试床按当前占位值构造并验证**；W7 校准若改阈值，
验证 gate（§4）会失败提示，需重调 case 或重验。语料须设计成对阈值有余量
（邻居放 2–3 个、query 明显弱召回），降低脆性。

## 3. eval cases + 标注

`data/gold_eval/agent_residual_eval.jsonl`（~10 条）：
```text
case_id、query、gold_doc_ids、gold_chunk_ids、expected_behavior、
corpus_source=agent_residual、split=agent_residual
```
旁路标注 `data/gold_eval/agent_residual_v1_annotations.jsonl`（**非评分**）：
```text
case_id、scenario_type(cooccurrence|weak_recall|policy_crowding|no_recovery|conflict)、
expected_failure_type、expected_legal_actions
```

## 4. 验证 gate（本任务的核心交付，零 token）

`tests/unit/test_agent_residual_testbed.py`：对每条 case，构造 first-pass（用真实/或
受控检索 + mock 答案），跑 `diagnose(first_pass)`，断言：

```text
1. diagnose(case).legal_actions == annotation.expected_legal_actions（逐条）
2. 共现 case 数（legal=={a,b,e}）≥ 6   ← 硬指标，不达标即 fail
3. 每条 case 的 gold_chunk_ids 在索引中存在且可检索到（gold 可达，使 success 可能）
```

这个 gate **证明测试床真有决策点**，是 P3-09 消融有意义的前提。

## 5. 语料与 query 草稿（Claude 提供）

Claude 按 §1/§2 起草 ~10 条的 topic + 3 文档结构 + 缩写 query + 期望诊断标注，
交付为可直接落盘的草稿（紧随本 spec 或单独消息）。Codex 落地文件 + §4 验证 + 泄漏检查。
**eval-author 隔离**：query 含区分性内容词但不抄 gold 答案句；过双向泄漏检查
（`check_eval_leakage.py`，含 §C2-05 的 no_retrievable_content 下限）。

## 6. 接入

- `dataset.py` / runner 支持 `agent_residual` split（loader + 索引开关，默认不进 headline）。
- gold 回填：Codex 据实际 chunk_id 回填 gold_chunk_ids。
- 不进任何 headline；该 split 仅供 P3-09 agent 消融使用。

## 7. 验收

```text
- agent_residual_corpus + agent_residual_eval.jsonl(~10) + annotations 落盘。
- 验证 gate 测试绿：逐条 legal_actions 符预期，**共现 ≥6**，gold 可达。
- 双向泄漏检查通过并归档。
- ruff + pytest tests/unit 全绿；不破坏既有 207；零 token。
- agent_residual 不进 headline 索引（断言）。
```

## 8. 不做

```text
- 不跑真实 eval / 不做 pass^k / 不做 replay。
- 不改 diagnosis 阈值（W7 校准时再动；本床按占位值构造 + 验证）。
- 不混入 external/fixture headline。
```
