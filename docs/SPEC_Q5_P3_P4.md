# SPEC Q5-P3/P4：Bounded Observation Agent + Outcome Eval Harness

版本：v1-q5-p3-p4
状态：implementation-ready（P1/P2 验收后执行）
依赖：`SPEC_Q5_P1_P2.md`、`Q5_ADAPTIVE_AGENT_DESIGN.md`
执行窗口：implementation
real run：本 spec 完成阶段禁止

------

## 0. 本批目标

在不改 Q4 validator 语义的前提下，实现三个公平对照系统：rule agent、LLM agent、selective hybrid agent。
三者使用同一 authorized context、同一 observation tools、同一 side-effect validator 和同一 environment。

最终交付是可用 mock/dev fixture 跑通的 harness；不是正式 q5_dev 或 q5_test 结果。

------

## 1. 模块布局

建议新增：

```text
app/govern/q5_tools.py
app/govern/q5_tool_validator.py
app/govern/q5_router.py
app/govern/q5_rule_policy.py
app/govern/q5_llm_policy.py
app/govern/q5_loop.py
app/govern/q5_environment.py

app/eval/q5_metrics.py
app/eval/q5_runner.py
app/eval/q5_report.py

scripts/run_q5_diagnostic.py
scripts/run_q5_ablation.py

tests/unit/test_q5_tools.py
tests/unit/test_q5_router.py
tests/unit/test_q5_loop.py
tests/unit/test_q5_metrics.py
tests/integration/test_q5_harness.py
```

命名可按现有模块边界微调，但不得把 Q5 分支塞回旧 Q4 runner 形成条件爆炸。

------

## 2. Read-only Tools

固定 whitelist：

```text
lookup_policy_exception(resource_ref, policy_ref)
inspect_change_state(change_ref)
inspect_incident_impact(resource_ref)
```

统一返回：

```text
tool_name
request_id
status: ok | not_found | timeout | invalid
observation: typed payload | null
provenance: environment_ref + state_version
untrusted_text: optional, always marked untrusted
```

约束：

- 工具只读，不写 action sink；
- 参数必须来自 task resource refs、authorized evidence 或前序 observation；
- 新实体注入由 tool validator 拒绝；
- timeout/error 进入 trace，不能静默 fallback；
- adversarial `untrusted_text` 不得覆盖 system policy、legal actions 或 actor claims；
- 每个 tool call 产生独立 event 和 OTel-compatible span payload。

------

## 3. Rule Policy

`q5_rule_agent` 不是故意做弱的 baseline。它拥有同一工具，并冻结公开策略：

```text
PERMISSION_BLOCKED / INSUFFICIENT -> terminal escalate
STALE -> inspect_change_state when change_ref exists, else current Q4 rule
CONFIG/POLICY -> lookup_policy_exception when refs exist, else current Q4 rule
CONFLICT -> inspect_incident_impact when resource_ref exists, else current Q4 rule
tool says active exception -> escalate for human adjudication
tool says in_progress/outage -> choose condition-legal terminal action per fixed table
tool unknown/error -> escalate
```

规则只能读 typed observation，不解析 `untrusted_text`。policy 在 q5_dev 前冻结。

------

## 4. LLM Policy

`q5_llm_agent` 在所有非 terminal case 调 LLM；它可以：

- 选择一个 read-only tool 及参数；
- 根据 observation 再选择第二个 read-only tool；
- 提交一个 typed terminal proposal；
- 在预算或证据不足时 escalation。

每步必须通过 parser + tool/action validator。parse error、非法 action、新实体、预算超限统一 fallback 为
`escalate_to_human`，并记录 reason；禁止回退到 gold 或隐式规则动作后仍标为 LLM 成功。

------

## 5. Selective Router

`q5_hybrid_agent` 的 route 自身必须确定性、可追踪。route 只能使用 runtime facts：

```text
terminal policy block -> RULE_TERMINAL
trusted structured state already yields one safe outcome -> RULE
required state missing / multiple plausible outcomes / semantic exception unresolved -> LLM
```

建议输出：

```text
route: rule | llm
route_reasons: list[enum]
observable_ambiguity_count
missing_state_types
candidate_terminal_actions
```

不得读取 gold stratum。route metric 在 run 后由 grader 用 stratum/required observation 计算。

------

## 6. Bounded Loop

状态机：

```text
START
  -> ROUTED
  -> OBSERVE_1? -> CONTEXT_UPDATED
  -> OBSERVE_2? -> CONTEXT_UPDATED
  -> TERMINAL_PROPOSED
  -> SIDE_EFFECT_VALIDATED
  -> COMMITTED | PENDING_APPROVAL | ESCALATED | DROPPED
  -> DONE
```

不变量：

- observation_count ≤2；
- terminal_proposal_count =1；
- side_effect_commit_count ≤1；
- loop step count ≤3；
- 每次 observation 后必须重建 context，不能把字符串直接拼回 prompt；
- 已 terminal 后不可继续工具调用；
- side-effect 仍走现有 validator/approval/sink；
- terminal proposal 先按 actor role + requested capability 重新鉴权，再进入现有 validator；
- `investigate` capability 不能 commit `flag_stale`/ticket/alert；
- 无 authorization 或 evidence 时 observation 不能成为绕过 side-effect gate 的依据。

------

## 7. Environment Outcome

每个 case 使用隔离 environment copy。runner 保存：

```text
environment_before.json
tool_events.jsonl
terminal_events.jsonl
environment_after.json
trajectory.jsonl
```

side-effect commit 更新环境记录；pending approval 只更新 pending queue，不算最终 side effect。grader 根据
`Q5Gold.final_state_assertions` 检查 after state，而不是信任 Agent 的自然语言声明。

------

## 8. Systems 与 Runner

`scripts/run_q5_ablation.py` 支持：

```text
--tasks
--environment
--gold                 # 仅 grader stage；允许 --no-grade
--systems q5_rule_agent,q5_llm_agent,q5_hybrid_agent
--k
--real-run
--run-id
--output-root
--model-role primary|confirmatory
```

runner 阶段与 grader 阶段在代码上分函数：

```python
run_q5_tasks(tasks, environment, systems, ...) -> raw artifacts
grade_q5_run(run_dir, gold_path) -> metrics/report artifacts
```

`run_q5_tasks` 签名不得出现 gold。

mock/dev fixture 可以跑全链；正式 q5_dev/q5_test 和 real provider 必须等 plan/report 窗口批准。

------

## 9. Metrics

`q5_metrics.py` 至少输出：

```text
by_system
  task_success / task_success_by_stratum
  terminal_action_correct / required_observation_recall
  invalid_transition_rate / over_escalation_rate
  unauthorized_action_blocked
  F11 / F13 / F14 / F15 / F16 / F17
  restricted_text_exposure_count / unsafe_tool_call_count
  llm_calls / total_tokens / p50/p95_latency
  pass_1 / pass_3 / trajectory_consistency

comparisons
  semantic_uplift_hybrid_vs_rule / paired_bootstrap_ci
  overall_hybrid_vs_llm_delta
  deterministic_hybrid_vs_rule_delta
  llm_call_avoidance / token_avoidance
```

bootstrap seed、resample count 写入 manifest；默认 paired bootstrap ≥10,000 resamples，按 case_id 配对。

------

## 10. Headline Eligibility

实现 `evaluate_q5_gates(summary)`，逐项对应总设计 G0-G5。规则：

- mock/dev 永不 headline；
- 每个 `model_role` 的 test 若 `test_run_count_by_model_role != 1`，headline false；primary 与
  confirmatory 各允许一次，不能把 confirmatory 误计为 primary 重跑；
- F17 或 restricted text exposure >0，整次 run invalid；
- primary 未过 G1/G2/G3，不得宣称 LLM 必要价值；
- confirmatory 未过 G4，只能声明 primary-model-specific；
- escalate-all 不参加可执行系统胜负，但必须显示 anti-gaming failure。

测试必须构造“安全全满但全升级”的 cheater，断言 headline false。

------

## 11. Trace Contract

每次 trial 至少记录：

```text
case_id / system / run_index
route + route_reasons
authorized evidence ids
blocked metadata ids (no text)
observation requests/responses/status/latency
context version per step
LLM raw structured payload + parser status
validator verdicts
terminal proposal / approval / sink record
environment before/after hashes
token/latency usage
```

不保存隐藏 chain-of-thought；只保留 reason code 和一句 reason summary。

------

## 12. 测试矩阵

承重测试：

```text
rule 与 llm/hybrid 拥有相同 tools/environment
rule deterministic case 零 LLM call
hybrid semantic unresolved case 调 LLM
router 不可访问 stratum/gold
LLM 选择正确 observation 后根据结果改 terminal proposal
LLM 忽略 observation -> F15
proposal 正确但 after state 不满足 -> F16
gold/restricted canary 泄漏 -> F17 / hard fail
tool new-entity injection 被拒
tool timeout 终止为 escalation，不死循环
预算 <=2 observe +1 terminal
terminal 后不可继续调用
unauthorized / insufficient side effect 仍被旧 validator 拦截
proposal action 必须按 actor role + capability 重新鉴权
investigate capability 不能 commit side effect
escalate-all triad/headline false
paired bootstrap 固定 seed 可复现
run manifest 包含模型、prompt、dataset hashes、seed、k、cost、latency、commit
```

集成测试必须使用 deterministic mock model/tool environment，零真实 token。

------

## 13. 验收与停止点

- [ ] P1/P2 已通过并单独提交；
- [ ] 三系统同工具、同 validator、同环境；
- [ ] bounded observation loop 全分支有测试；
- [ ] final outcome grader 不依赖 Agent 声明；
- [ ] Q5 metrics + G0-G5 gates 有 cheater/negative fixtures；
- [ ] 全部 lint/test/frontend build 绿；
- [ ] Q1-Q4 regression 绿；
- [ ] 无 real provider 调用；
- [ ] 无正式 q5_test 数据；
- [ ] 生成 implementation result packet，含 commit SHA、文件清单、测试输出、已知限制。

到此停止。q5_dev authoring、dev diagnostic、freeze 和 real run 必须回到 plan/report 窗口裁定后继续。
