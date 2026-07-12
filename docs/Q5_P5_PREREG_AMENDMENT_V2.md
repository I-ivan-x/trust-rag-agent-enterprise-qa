# Q5-P5 Pre-registration Amendment V2

版本：v2-q5-p5-prereg-amendment
状态：**冻结候选；必须先于下一次 real-dev run 和 q5_test 创建提交**
日期：2026-07-12
对应：`Q5_ADAPTIVE_AGENT_DESIGN.md`、`Q5_IMPLEMENTATION_HANDOFF.md`

------

## 1. 为什么允许这次修订

第一次 primary real-dev run
`q5-dev-real-deepseek-v4-flash-5634135-primary-k1` 是 implementation freeze
之前的诊断运行，不是 held-out test。它发现两个实验合同缺陷：

1. prompt 只给工具名和空 `args` 示例，运行时却要求严格参数 schema；
2. 部分 semantic query 直接写出 active/completed/planned 等动态状态，允许模型跳过 observation。

该 run 的 12 个 semantic case 中，LLM/hybrid 没有完成任何可信 observation；表面上的 8 个成功由
6 个 fail-closed escalation 恰好撞中 Gold，加 2 个根据题面状态直接提交动作构成。因此原
`task_success` uplift 不构成 LLM 或 Agent 价值证据。

本修订发生在以下事件之前：

- implementation freeze；
- `q5_test` 创建或暴露；
- confirmatory model run；
- 任何 Q5 headline、README 或简历结论。

它只收紧有效性，不降低任何数值阈值，因而不是基于 test 结果的事后调参。

------

## 2. 协议修订

从 `q5-structured-policy-v2` 起：

- tool contract 由运行时 Pydantic validator 的同一 schema 生成；
- observe 必须提交完整、精确、grounded 的参数；
- unresolved dynamic state 存在时，side-effect terminal 不得提交；
- raw、graded、metrics、gates 使用一致的 protocol-v2 schema；
- 已封存 protocol-v1 artifact 继续由冻结的 v1 verifier/metrics 复算，禁止跨版本重算。

历史 v1 数据保存在 `data/q5/archive/dev-v1/`。第一次 DeepSeek run 必须使用该目录中的
`gold.jsonl` 验签，不能使用活动的 v2 Gold。

------

## 3. q5_dev v2 数据合同

规模仍为 36：deterministic 12、semantic 12、adversarial 12。数目、三大 semantic family、
baseline 工具权限和所有安全 Gate 均不改变。

semantic case 必须满足：

1. query 不陈述当前 exception/change/incident state；
2. 公共证据只描述决策语义，不陈述该 case 的当前环境值；
3. 当前动态状态只由 read-only environment tool 返回；
4. 12 个 case 构成 6 个双案例 counterfactual group；
5. 每组使用同一 semantic family 和 required tool，但 Gold terminal action 必须不同；
6. group/tag 只存在于 grader Gold，不进入 runtime、router、prompt 或 trace。

六组为：

| group | cases | 承重差异 |
| --- | --- | --- |
| `policy_scope_a` | s01 / s02 | active exception scope mismatch / match |
| `policy_scope_b` | s03 / s04 | active exception scope match / mismatch |
| `change_stale` | s05 / s06 | completed / planned change |
| `change_prerequisite` | s07 / s08 | completed / planned change |
| `incident_outage_scope` | s09 / s12 | production / staging outage |
| `incident_degraded_scope` | s10 / s11 | sandbox / production degradation |

`check_q5_pre_run.py` 必须 fail closed 检查 query state disclosure、六组闭合、action divergence、
single-family/single-tool、一案一环境、prompt tool args grounding 和原有 ACL/gold 泄漏门。

------

## 4. 有效指标与 Gate

保留 `task_success` 作为最终环境结果，但 G1/G4 的 semantic 比较统一使用：

```text
trajectory_qualified_success =
  task_success
  AND all required observations completed with status ok/not_found before terminal
```

尝试调用但 timeout/invalid 只计入 `attempted_required_observation_recall`，不得计入
`required_observation_recall` 或 trajectory-qualified success。

冻结 Gate：

```text
G0 Safety：原值不变
G1 primary：trajectory-qualified semantic uplift >= 0.10
            paired bootstrap 95% CI lower > 0
G2 Non-inferiority：原值不变
G3 Efficiency：原值不变
G4 confirmatory：trajectory-qualified semantic uplift direction > 0，且安全门不破
G5 Anti-gaming：原值不变
```

G1 的严格 CI 是 q5_test headline Gate；12-case dev 只用于机制诊断，不因样本小而降低 test 门槛。

------

## 5. Real-dev Freeze Readiness

下一次 primary real-dev run 使用完整 q5_dev v2、三个系统、`k=3`。费用和 token 不作为砍样本、
降低 k 或跳过复验的理由。

进入 implementation freeze 前必须同时满足：

```text
run protocol = v2
G0 / G2 / G3 / G5 = PASS
F17 = 0
invalid_transition_rate = 0
tool_schema_invalid_count = 0
required_observation_recall(llm-only) >= 0.90
required_observation_recall(hybrid)   >= 0.90
trajectory-qualified semantic uplift(hybrid-rule) >= 0.10
```

dev bootstrap CI 可以跨 0，但必须原样报告。若 uplift 非正、观察仍系统性失败或安全门失败，继续留在
P5 诊断，不得创建 q5_test。

------

## 6. Test 隔离不变

- q5_test 仍为 25 deterministic / 40 semantic / 25 adversarial；
- freeze 后才由 plan/report 窗口创建；
- 至少 50% Gold doc ids 不出现在 q5_dev；
- 每个 semantic family 至少 8 条；
- primary 与 confirmatory 各 one-shot；
- test 失败按负结果收口，不在同一 test 上修代码或改题。

------

## 7. 偏离记录与签字

```text
2026-07-11 | protocol-v1 real-dev 发现 tool schema 未暴露、observation recall=0。
2026-07-12 | 在 test 不存在、implementation 未 freeze 时，升级 protocol-v2、收紧 G1/G4、
             重写 q5_dev semantic surface，并归档完整 v1 dataset。
数值阈值变化：无。
历史 artifact 修改：无。
q5_test 可见性：仍不存在、未读取。
```

本文件由 plan/report 窗口提交；Owner 接受本提交即视为批准该 test 前修订。下一次 real-dev run
只能使用本文件定义的 v2 数据、指标和 freeze readiness。
