# Q5-P0 Diagnostic：为什么旧任务无法证明 LLM 的必要价值

版本：v1-q5-p0-static-diagnostic
日期：2026-07-10
模式：static / zero-token / no sink / no code change
证据范围：Q2-Q4 报告、36 条 ops dev+test case、当前 controller/context/runner/validator 实现

------

## 0. 诊断结论

Q2-Q4 的 `rule ≈ llm` 不能被解释为“LLM 对 Agent 没有价值”。更准确的结论是：

> 当前任务、数据合同和 controller 接口把动作选择预先压缩成了 condition→action 的确定性映射；
> LLM 既看不到足够的语义证据，也没有多轮环境反馈，因此没有独占的认知工作可以完成。

Q5 不应先换更强模型或增加 prompt，而应先修复四个实验结构问题：

1. runtime 不得读取 gold；
2. 同一 condition 必须出现多个依赖上下文的合法 outcome；
3. LLM 必须能读取经过 ACL 过滤的证据正文与可信工具观察；
4. Agent 必须根据工具结果进行有限调整，并按最终环境状态评分。

------

## 1. 机械统计

盘点集合：

- `ops_runbook_action_v1_eval.jsonl`：14 条；
- `ops_runbook_action_v1_dev_additions.jsonl`：2 条；
- `ops_runbook_action_v1_test.jsonl`：20 条；
- 合计：36 条。

### 1.1 每个 condition 只对应一个 gold action

| gold condition | cases | unique gold action |
| --- | ---: | --- |
| `STALE_PROCEDURE` | 8 | `flag_stale` |
| `CONFIG_VIOLATION` | 5 | `open_remediation_ticket` |
| `BROKEN_XREF` | 3 | `open_remediation_ticket` |
| `MISSING_PREREQ` | 2 | `open_remediation_ticket` |
| `ACTIVE_ACTIVE_CONFLICT` | 5 | `send_alert` |
| `PERMISSION_BLOCKED` | 6 | `escalate_to_human` |
| `INSUFFICIENT_EVIDENCE` | 3 | `escalate_to_human` |
| `none` | 4 | `no_op` |

`ActionCount=1` 对全部 condition 成立。只要 condition detector 正确，规则查表就是最优策略；LLM
没有机会利用上下文做出不同但更正确的选择。

### 1.2 28/36 case 的 requested action 可能回退读取 gold

`app/eval/govern_runner.py::_requested_action()` 先从 query 中查找少量动作关键词；若未命中，则读取
`case.gold_action` 作为 `ActorContext.requested_action`。机械扫描中，28/36 条 query 未命中当前关键词表。

这意味着 gold label 可能进入 authorization/detection 路径。它不必然改变每个 case 的最终动作，但违反
“gold 只供 grader 使用”的评测合同。Q5 必须将 task input 与 gold 完全分离，并加入机械泄漏测试。

### 1.3 LLM 看不到证据正文

`GovernanceControllerContext.neighborhood` 当前只包含：

```text
chunk_id · doc_id · status · section_path
```

它不包含 chunk text、rerank score、policy relation、证据摘录或工具 observation。LLM prompt 虽然包含
`QUERY`、`SIGNALS`、`LEGAL_ACTIONS` 和 `NEIGHBORHOOD`，但可用于语义判断的正文证据不存在。

同时，`LEGAL_ACTIONS` 已由规则 condition 和代码表提前裁剪；多数 case 中 LLM 实际只是在“固定动作”与
`escalate_to_human` 之间选择。当前 LLM arm 更像带随机性的查表器，而不是语义决策器。

### 1.4 当前治理路径是单步执行

现有路径为：

```text
retrieve -> detect_conditions -> controller.select -> validator -> sink
```

工具执行结果不会回到 controller，Agent 不会基于环境变化选择下一步；MCP server 提供工具包装，但
治理主路径直接调用本地 sink，没有经过真实 MCP client/tool-observation loop。

因此，现有系统充分证明了受治理的动作执行，却只部分证明了 Agent 的动态适应能力。

------

## 2. 根因归类

| 现象 | 不是根因 | 真正根因 |
| --- | --- | --- |
| rule 多次等于或优于 LLM | 模型一定太弱 | condition→action 一一映射，LLM 没有决策空间 |
| LLM 增加 jitter | temperature 不够低 | prompt 输入缺少证据正文，选择仍受预裁剪动作表限制 |
| Q4 规则控制器达标 | 项目本质只是 workflow | 当前承重任务适合 workflow；尚未构造语义 frontier |
| Agent 只执行一次动作 | 动作预算太小 | 没有 read-only observation→replan 的状态循环 |
| authorization 指标稳定 | intent resolver 很可靠 | eval 路径可能从 gold_action 回填 requested action |

------

## 3. Q5 设计决策

根据以上诊断，Q5 冻结以下方向：

1. **不改写 Q2-Q4 结论。** 旧任务上 LLM 无增益仍是有效负结果。
2. **不以 always-LLM 为目标。** 新 headline 是 selective hybrid，而不是让 LLM 控制全部流程。
3. **旧 validator 安全合同不动。** side-effect proposal 仍必须经过独立 validator/HITL。
4. **新增 observation loop。** 最多 2 次 read-only tool observation，再给出 1 个 terminal proposal。
5. **新增 semantic frontier。** 同一 condition 在不同上下文下允许 act 或 escalate，不能再由 condition
   唯一决定 gold outcome。
6. **按 outcome 评分。** transcript 看似正确不算成功，必须检查最终 environment state。
7. **运行输入与 gold 物理分离。** runner 只能加载 task input；grader 单独加载 gold。
8. **LLM 只看授权信息。** blocked chunk 只暴露计数/ID/原因，不把受限正文放入 prompt。

------

## 4. 不可违反的红线

- `gold_action`、`gold_final_state`、`stratum`、`required_observations` 不得进入 runtime context。
- implementation 窗口只可读取 `q5_dev`；`q5_test` 在实现冻结后由 plan/report 窗口生成。
- 不以增加工具调用次数、链长或 Agent 数量作为能力证明。
- 不放松 F11/F13、ACL、evidence gate、risk tier 或 approval 约束。
- 不基于 q5_test 的逐 case 结果修代码；若一次性 test 未过，Q5 按负结果收口，后续必须新建 test。
- Q5 新代码不得改变 Q1-Q4 frozen runner 的历史结果与接口语义。

------

## 5. Diagnostic Gate

Q5 可以进入设计/实现阶段，因为已确认：

- [x] LLM 无增益的主要结构性原因可定位；
- [x] 新阶段问题与 Q4 残留问题不同，不是重复调参；
- [x] 可在不削弱安全控制面的前提下增加 Agent 动态能力；
- [x] 可设计 rule-only / llm-only / selective-hybrid 同条件对照；
- [x] 可用新 corpus surface 和 outcome grader 形成独立证据。

诊断决议：**进入 Q5 Adaptive Hybrid Agent。**
