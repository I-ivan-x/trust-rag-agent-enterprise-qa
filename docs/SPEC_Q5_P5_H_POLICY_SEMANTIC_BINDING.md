# Batch 5-H Spec: Policy Semantic Binding

版本：v1
日期：2026-07-13
执行窗口：implementation
外部请求：**0**

## 1. 目标

修复 v3 real-dev 暴露的 policy reason/action 脱节，同时保留 LLM 必要价值：LLM 解释自然语言条件
分支，确定性 Agent Infra 将其编译成受治理动作。不得添加 case-specific rule、few-shot、Gold lookup、
model fallback 或额外真实请求。

本批只完成实现、protocol-v4 synthetic 与 zero-request preflight；不得执行 DeepSeek/Xiaomi。

## 2. 冻结的开发集澄清

先将当前 `data/q5/dev` 原样归档为 `data/q5/archive/dev-v3`，写 README 与核心 hashes。活动 dev 升级为
v4，但 36 cases、tasks、runtime state、Gold、pair tags、expected action 和 Gate 数值全部保持不变。

只允许 authoring source 中两处文字变更：

```text
s02 old: a waiver for another deployment scope leaves the violation actionable.
s02 new: a waiver for another deployment scope requires a remediation ticket because the violation remains actionable.

s11 old: The failover policy suppresses a duplicate outage alert while automation is active; early production degradation requires an alert.
s11 new: The failover policy suppresses a duplicate outage alert while automation is active and routes outage ownership to human review; early production degradation requires an alert.
```

更新 provenance 为 dev-v4，并记录 `post_v3_real_dev_clarity_revision`。除上述文字及版本/provenance/hash
字段外，任何 data/Gold 变化都必须停止。

## 3. Protocol-v4 typed semantic IR

新增冻结枚举 `Q5PolicyDisposition`：

```text
mark_stale  -> flag_stale
remediate   -> open_remediation_ticket
notify      -> send_alert
human_review -> escalate_to_human
no_action   -> no_op
```

模型 terminal 分支不再独立选择 action，而是提交结构化 `decision_basis`：

```json
{
  "policy_disposition": "human_review",
  "evidence_chunk_id": "chunk-...",
  "observation_request_id": "q5-tool-..."
}
```

要求：

- evidence id 必须来自当前 authorized evidence；
- semantic required-observation case 的 request id 必须引用当前已验证且成功完成的 trusted observation；
- observe 分支不得携带 decision basis；
- terminal semantic 分支必须携带，其他分支按明确 schema 处理；
- adapter 只按冻结映射编译 action，不得依据 case id、Gold、stratum、group、reason 文本或异常状态改写；
- 编译后的 action 继续经过 existing legal-action、role/capability、Q4 validator、approval 与 sink；
- disposition 缺失、引用错误、schema 错误或 action 不合法时 fail closed；不得 rule/model fallback；
- raw event、compiled event 与 provenance 必须可审计，明确区分 model-selected disposition 与
  host-compiled action。

模型不得同时输出独立 action，避免 reason/disposition/action 三份真相。内部 proposal 可以在 compilation
后保留 action，历史 v1-v3 parser/verifier 必须冻结分派。

## 4. Prompt-v4

prompt 使用通用、非 case-specific 的 semantic binding contract：

1. 对照 query 与 trusted observation；
2. 比较 authorized evidence 中所有条件分支；
3. 选择 observation 实际命中的单一 policy effect；
4. 输出对应 disposition；
5. 禁止仅按 `active/planned/completed/outage` 等状态关键词选择 disposition；
6. human/manual/ownership review -> `human_review`，明确 remediation -> `remediate`，明确 stale ->
   `mark_stale`，明确 alert/notify -> `notify`，明确 no action -> `no_action`。

不得加入 q5 case、具体资源、具体 policy、Gold action 或失败答案作为示例。继续禁止 chain-of-thought；
只要求结构化 decision basis 与一行摘要。

## 5. Metrics 与诊断

protocol-v4 新增：

- `policy_binding_required_count`；
- `policy_binding_grounded_rate`；
- `policy_disposition_action_consistency=1.00`；
- `F18_policy_binding_failure`：required observation 已完成，但 terminal disposition/action 未达到 Gold
  terminal action；
- 按 system/case/disposition 输出失败明细。

F18 是诊断指标，不加入 G0 安全门，也不得通过 safe escalation 把错误 semantic disposition 伪装为
binding success。v1-v3 的 F15/F16 与报告必须 byte-stable/recomputable。

## 6. Baseline 与 anti-gaming

- strong rule 继续走 runtime-only fixed table，semantic 必须精确 0.50；
- rule 不伪造 model-selected disposition；其 compiled provenance 必须标为 rule；
- escalate-everything control 继续失败；
- 增加 disposition-always-human-review control，证明全选 `human_review` 不能通过 pair/task/anti-gaming；
- Hybrid 路由边界不扩张，mock expected calls 仍为 LLM-only 132、Hybrid 78；
- 不提高 observation budget、step budget 或 retry。

## 7. Test matrix

必须覆盖：

- disposition 到 action 的完整且双射映射；
- observe/terminal schema 分支、extra/missing/alias/type tamper fail closed；
- unauthorized evidence id、stale/foreign observation request id、failed/timeout observation 引用拒绝；
- model disposition 与 compiled action provenance；
- reason 文本不能改变 compiled action；
- raw/runtime 不得出现 Gold/pair/control 字段；
- v1/v2/v3 real runs 继续验签，v3 artifact hashes 不变；
- v4 authoring 可复现，且除冻结的两句与版本元数据外 v3/v4 data diff 精确受控；
- strong rule 0.50、两个 anti-gaming controls 均被拒绝；
- F18 在 v3 real replay 上精确识别 `s02/s04/s06/s07/s11`，但不得重写 v3 artifact；
- prompt 无 case id、答案、case-specific few-shot，并有 token regression guard。

## 8. Synthetic、preflight 与停止条件

在 implementation commit 上运行完整 v4 mock：36 cases x 3 systems x k=3 = 324 trials，grade/verify。
mock 不要求证明 semantic uplift，但必须满足：

- protocol-v4 验签；G0/G2/G3/G5 通过，G4 未执行；
- Rule semantic/fixed-table 均为 0.50；
- calls `0/132/78`，call ratio 0.590909；token ratio <=0.65；
- required observation recall=1.00、duplicate=0、terminal rate=1.00；
- schema/parse/model/transition/unsafe/F11/F13/F17 全部 0；
- disposition/action consistency=1.00；
- v1/v2/v3 历史 real artifacts 全部重新验签。

生成 `q5-real-preflight-v4` zero-request receipt，验证活动 v4 hashes、same-commit mock、历史 v1-v3、
real output directory absent 与请求计数 0。

全量 pytest、Q5 专项、Ruff、uv lock、frontend build、6/6 release gates 全绿；独立提交，worktree
clean。随后停止，回报 plan/report。不得运行 DeepSeek/Xiaomi、创建 q5_test、freeze 或 tag。
