# Q5-P5 Real-dev V2 Negative Diagnostic

版本：v1
日期：2026-07-12
状态：**EVIDENCE-BACKED NEGATIVE RESULT; V3 FOLLOW-UP ACTIVE**

## 1. 审核结论

Commit `2224fc441bb9b333440f1cdbcb10f8f9652350ee` 与唯一 DeepSeek primary run 均审核通过。
run 为 protocol-v2、real、无 mock/fallback/retry，324/324 trials 完成，四类 artifact 可交叉重算。
NOT FREEZE READY 裁决正确，不是执行失败。

## 2. 失败分解

| Surface | LLM-only calls | Hybrid calls | LLM-only success | Hybrid success |
| --- | ---: | ---: | ---: | ---: |
| Deterministic | 33 | 0 | 36/36 | 36/36 |
| Semantic | 82 | 82 | 21/36 | 21/36 |
| Adversarial | 30 | 9 | 36/36 | 36/36 |

Hybrid 仍只在预定 39/108 trials 调模型；G3 不是 router 扩张，而是被路由 case 的 step 数增加。
LLM-only 与 Hybrid 各有 13 条三调用轨迹。若成功 observation 后不允许重复同一调用，调用量上界回到
mock 的 `132 / 78`，call ratio 回到 `0.590909`。因此 G3 有明确 Agent-loop 修复路径。

Semantic 失败稳定集中于 `s01/s04/s06/s10/s12`，每案两个系统均 3/3 失败。模型已经取得正确工具
状态，但没有可靠执行 scope、change lifecycle 与 incident environment 的组合语义。`s04` 还在相同
成功 observation 后重复调用直至预算耗尽。

## 3. 更重要的有效性问题

v2 semantic family 可以被固定状态表表达：

```text
policy active + scope match -> escalate；否则 remediate
change completed -> side effect；planned -> escalate
incident production + degraded/outage -> alert；否则 escalate
```

因此即使继续 prompt tuning 让 LLM 达到 1.00，评审仍可用一个很小的强规则 baseline 攻击“LLM 必要
价值”。当前 rule baseline 没有实现这张表，属于偏弱对照。下一阶段不能只修 prompt 或为失败 case
补示例；必须把 semantic frontier 改成同时满足：

1. 同一 policy、不同 observation 导致不同动作，证明 adaptation；
2. 相同 observation、不同自然语言 policy 导致不同动作，证明 semantic interpretation；
3. 固定全局状态表无法解决，但 LLM 仍只能提出 typed proposal；
4. 工具、validator、side-effect guard 和 state machine 继续掌握最终权限。

这一路线不会把系统改成规则工作流。规则负责不可协商的安全和循环完整性，LLM 负责无法由固定表枚举
的授权文本解释与动态状态组合判断。

## 4. 下一阶段边界

Batch 5-E 已用零外部请求完成 Agent/eval validity groundwork，并确认 v2
`fixed_table_solvability=1.00`。后续活动合同已转移到 `Q5_P5_PREREG_AMENDMENT_V3.md` 与
`Q5_P5_DEV_V3_AUTHORING_REPORT.md`；本报告继续作为 v2 负结果记录。

完成并审核后，由 plan/report 窗口单独 author q5_dev v3 与第二次 test-before-seeing amendment。
