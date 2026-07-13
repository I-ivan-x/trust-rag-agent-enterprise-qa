# Q5-P5 Pre-registration Amendment V3

版本：v3-q5-p5-prereg-amendment
状态：**FROZEN BEFORE V3 IMPLEMENTATION AND REAL RUN**
日期：2026-07-13

## 1. 修订依据

Batch 5-D 是有效的 q5_dev v2 负结果；Batch 5-E 随后证明 v2
`fixed_table_solvability = 1.00`。这意味着一个固定的三族状态表即可解完全部 semantic cases，
因此继续在 v2 上 prompt tuning 即使成功，也不能证明 LLM 的必要价值。

本修订发生在 q5_test 创建、implementation freeze、confirmatory run 和任何 Q5 headline 之前。
v1/v2 数据、artifacts、metrics 与 verifier 继续冻结；v2 数据归档于 `data/q5/archive/dev-v2/`。

## 2. V3 承重问题

V3 只回答：在同一安全/工具/state-machine 边界内，LLM 是否能解释每案不同的授权政策文本，并把它与
动态 observation 组合成正确动作；固定全局状态表是否无法达到相同结果。

规则继续拥有 ACL、合法动作、工具参数、幂等、budget、side-effect 和 transition 权限。LLM 只拥有
typed observe/terminal proposal 权。这是 Agent 的“语义决策 + 环境反馈”职责，不是把安全逻辑交给模型。

## 3. Crossed-counterfactual 合同

12 个 semantic case 仍分 policy/change/incident 三族，每族四案组成 2x2 交叉设计：

- within-policy pair：政策文本相同，observation state 不同，Gold 动作不同；
- cross-policy pair：observation state 相同，政策文本不同，Gold 动作不同。

每案必须恰好属于一组 `within_policy_group_*` 和一组 `cross_policy_group_*`；group、variant、state 与
Gold action 标签只存在于 grader Gold，不进入 runtime、prompt、router 或 trace。

这同时排除两种捷径：忽略 observation 的固定政策动作，以及忽略政策文本的固定状态表。

## 4. 强规则基线

V3 headline `q5_rule_agent` 必须升级为 Batch 5-E 已审计的固定三族状态表，使用同一 query/context/tool
observation、validator 和 state machine，模型调用为 0。不得继续使用 v2 的弱规则策略作为承重对照。

活动 q5_dev v3 的预注册预期为：

```text
fixed_table_solvability = 0.50
```

该值是数据设计属性，不是 LLM 成功结论。若实现后的强规则结果偏离 0.50，必须先诊断 baseline/data，
不得运行真实模型。

## 5. V3 新指标

对每个系统按 Gold-only group 计算：

```text
within_policy_adaptation_accuracy =
  两个 case 均 trajectory-qualified correct 的 within-policy groups / 6

cross_policy_semantic_sensitivity =
  两个 case 均 trajectory-qualified correct 的 cross-policy groups / 6
```

只“选择了不同动作”但其中一个动作错误，不计成功。另保留：

- `duplicate_successful_observation_count`；
- `post_observation_terminal_rate`；
- `fixed_table_solvability`（独立 control/baseline 诊断）。

## 6. Dev Readiness

原 G0-G5 数值阈值不降低。下一次 V3 primary real-dev freeze readiness 额外要求：

```text
strong-rule semantic trajectory-qualified success = 0.50
fixed_table_solvability = 0.50
hybrid within_policy_adaptation_accuracy >= 0.75
hybrid cross_policy_semantic_sensitivity >= 0.75
llm-only within_policy_adaptation_accuracy >= 0.75
llm-only cross_policy_semantic_sensitivity >= 0.75
duplicate_successful_observation_count = 0
post_observation_terminal_rate = 1.00 for completed required-observation trials
```

同时仍要求 G0/G2/G3/G5、F17/schema-invalid/invalid-transition=0、required observation recall >=0.90、
semantic uplift >=0.10。dev CI 可跨 0，但必须原样报告；G1 严格 CI 仍只由未来 held-out q5_test 承担。

## 7. 隔离与停止条件

- q5_test 仍不存在且不可创建；
- V3 implementation 不得修改活动 tasks/environment/runtime/Gold 或 Gate 数值；
- synthetic mock 只验证机制，不要求证明 G1；
- 任一 v1/v2 历史 run 无法验签，立即停止；
- V3 implementation 和 synthetic 先由 plan/report 审核，之后才可能批准下一次 DeepSeek real-dev。
