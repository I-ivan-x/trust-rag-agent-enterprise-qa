# Q5-P5 Real-dev V3 Negative Diagnostic

版本：v1
日期：2026-07-13
状态：**VALID NEGATIVE RESULT; NOT FREEZE READY**

## 1. 审核结论

唯一 DeepSeek primary run 锚定 commit
`e54c42e84e39102b4c82bc1e19c85499270d18db`，完成 324/324 trials。protocol-v3、
trusted real client、无 mock/retry/fallback；v1/v2/v3 均在当前 verifier 下重新验签通过。

G0/G2/G3/G5 通过，G1 失败，G4 未执行。NOT FREEZE READY 裁决正确，不得 freeze、运行
confirmatory 或创建 q5_test。

核心 artifact SHA-256：

| Artifact | SHA-256 |
| --- | --- |
| `manifest.json` | `b0efd5a7a3c9d2f19cfe3251ed48c2d567a0336f9c779bf147434db8a1ce8de6` |
| `summary.json` | `86d6637954fa695e3de2d28d170ce3fb22f096ac360a18bf35e2f1f31d6f05a8` |
| `gates.json` | `1615fb0ecaf2fe44265f2f1c95a7707bef1a05acd3a4eb7c88debe89e4df15b9` |
| `report.md` | `387dfd50592a88e1859ac64e04e324dfe1d7b5257fb6fff7610c85aa697809cd` |

## 2. 有效机制证据

- Rule semantic 为 0.50，固定状态表不再能解决 crossed semantics；
- LLM-only/Hybrid required observation recall 均为 1.00；
- duplicate successful observation 为 0，post-observation terminal rate 为 1.00；
- Hybrid call/token ratio 为 `0.590909 / 0.644393`；
- F11/F13/F17、unsafe tool、invalid transition、schema/parse/model error 均为 0；
- Hybrid 与 LLM-only 在 semantic 上完全同结果，证明 router 没有掩盖 semantic 失败。

因此 Agent loop、观察完成协议、安全边界和选择性调用机制已经成立。失败面不是“没有观察”或“工具
失效”，而是观察完成后的 policy-to-action binding。

## 3. 真实失败模式

失败稳定集中于 `s02/s04/s06/s07/s11`，两个模型系统均 3/3 复现：

| Case | Observation | Policy effect expected | Actual |
| --- | --- | --- | --- |
| `s02` | active waiver, staging vs production | violation remains actionable -> remediate | escalate |
| `s04` | active tracking exception, scope mismatch | human ownership review | remediate |
| `s06` | replacement planned | human review | mark stale |
| `s07` | replacement completed | human archival review | mark stale |
| `s11` | production outage | suppress duplicate alert / ownership review | alert |

模型 reason 多数已经复述了正确 observation 或 policy clause，却仍按状态关键词选择动作。例如：

- `s07` reason 同时写出 “requires human archival review”，action 仍是 `flag_stale`；
- `s11` reason 写出 “suppresses duplicate alert”，action 仍是 `send_alert`；
- `s02` reason 写出 scope mismatch 与 “violation actionable”，action 仍是 escalation。

这不是缺少 chain-of-thought 的证据，而是当前输出合同只约束 action 合法性，没有要求模型把命中的
自然语言策略分支结构化绑定到 action。模型可以在 reason 与 action 之间自相矛盾，而 validator 无法
拒绝。

## 4. 评测自身的薄弱点

`s02` 的 “actionable” 没有明确写出 remediation ticket；`s11` 的 “suppress duplicate alert” 没有明确
写出后续 human ownership。Gold 虽与 author intent 一致，但外部评审可以合理攻击其 action mapping
不唯一。

下一版 dev 只允许澄清这两句自然语言，不改 case、Gold action、observation、pair、状态或 Gate。该修订
明确标记为看过 v3 real-dev 后的开发集修订，不能伪装成 held-out 证据。正式 q5_test 必须在 implementation
freeze 后重新独立 author。

## 5. 诊断盲区

当前 F15 只统计 missing observation、tool/policy error 或 budget exhaustion。五个 case 均成功完成
observation，因此 F15=0；F16 只统计 action 正确但最终状态错误，因此也为 0。报告没有机械分类
“observation complete but selected policy branch/action wrong”。protocol-v4 必须新增独立的 policy-binding
failure，不回写冻结的 v1-v3 指标。

## 6. 下一方向

Batch 5-H 引入 Policy Semantic Binding：

1. LLM 从授权 evidence、query 与 trusted observation 中选择有限 policy disposition；
2. disposition 携带 evidence chunk 与 observation request 的 grounded references；
3. 宿主侧以固定映射编译为治理 action，而不是让模型同时输出可能矛盾的 reason/action；
4. 原 validator、ACL、legal-action、approval、side-effect guard 继续执行；
5. 不增加 observation、模型调用、case-specific few-shot 或答案提示。

这会更突出 Agent：LLM 负责非结构化 policy interpretation，Agent Infra 负责状态采集、typed IR、动作
编译、权限与执行安全。它不是把 semantic frontier 改写成规则工作流。
