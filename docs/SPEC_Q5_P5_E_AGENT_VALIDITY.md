# Batch 5-E Spec: Agent Loop and Evaluation Validity

版本：v1
日期：2026-07-12
执行窗口：implementation
外部请求：**0**

## 1. 目标

一次完成四个闭环：让 observation loop 对成功结果幂等收敛；证明 v2 是否可被强固定规则表解决；把
real-run 轨迹诊断机器化；为 crossed-counterfactual q5_dev v3 提供版本化指标与协议骨架。

## 2. Observation Completion Guard

- 为成功的 `(tool, canonical args)` 建立 completed-observation key；
- 同 key 的 `ok/not_found` observation 不得再次暴露为可用调用；timeout/error 不视为完成；
- required observations 全部完成后，下一步 prompt 必须 terminal-only；
- controller 仍调用 LLM 选择 terminal action，不得由规则替模型决定动作；
- 重复 proposal 必须 fail closed 并产生明确 reason，不得执行第二次工具调用；
- 增加 `duplicate_successful_observation_count`、`post_observation_terminal_rate`。

## 3. Strong-rule Solvability Audit

新增 grader-only analytic control `q5_semantic_table_rule_control`：

- 只能读取 runtime 可见 query/context/tool observation，不得读取 stratum、Gold、family/group tags；
- 实现 v2 三族固定状态表，不做自然语言 LLM 调用；
- 走同一 tool executor、validator、terminal state machine 和 outcome grader；
- 不进入 headline 三系统，不影响 G0-G5，只输出 `fixed_table_solvability`；
- 在现有 q5_dev v2 synthetic 上预期 semantic success 接近或达到 1.00。若未达到，报告实际边界，
  不得读取 Gold 修补。

该 control 的用途是检验 baseline 攻击面，不是新增产品路径。

## 4. Real-artifact Replay Diagnostic

新增只读脚本，对已验签 run 生成机器报告：

- 输入必须通过 `verify_q5_graded_run`；
- 输出 per-case/system/run-index 的 observation sequence、重复调用、terminal action、Gold outcome；
- 汇总 decision invariance、counterfactual pair adaptation、三调用来源和按 stratum 的 call/token；
- 支持计算“成功 observation 后最多一次 terminal call”的 calls-only counterfactual 上界；
- 不重新调用模型，不改写原 artifact，不把 reason_summary 当 Gold。

必须用 Batch 5-D real run 固化 regression fixture/assertions：13 条三调用轨迹、semantic `82/82` calls、
五个稳定失败 case 与 calls-only ratio `0.590909`。

## 5. Protocol-v3 Groundwork

为未来 v3 新增但暂不启用：

- `within_policy_adaptation_accuracy`；
- `cross_policy_semantic_sensitivity`；
- `fixed_table_solvability`；
- `duplicate_successful_observation_count`；
- `post_observation_terminal_rate`。

v1/v2 models、metrics 和 verifier 必须冻结保持原验签结果。若严格 schema 需要新版本，完整建立 v3
分派，不得向 v2 artifact 追加字段。当前 q5_dev v2 run 仍按 v2 验签。

## 6. 红线与验收

- 不修改 `data/q5/dev`、Gold、Gate 数值、router、model identity 或历史 artifacts；
- 不创建/读取 q5_test；不运行 DeepSeek/Xiaomi；
- 不针对 `s01/s04/s06/s10/s12` 添加 prompt 示例或动作答案；
- v1 第一次 real run、v2 Batch 5-D real run 均重新验签通过；
- 新旧 Q5 专项、全量 pytest、Ruff、uv lock、frontend build、release gates 全绿；
- 独立提交，worktree clean；回报 strong-rule control 与 replay diagnostic 的完整结果。

任一冻结 verifier、历史 hash 或安全行为退化则停止，不进入 q5_dev v3 authoring。
