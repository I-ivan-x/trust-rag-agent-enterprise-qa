# SPEC Q3-P3 + P4：动作 validator + 风险路由/人审流 + 双控制器

版本：v1-q3-p3p4-impl
状态：实现规格（freeze-ready）。依赖 P1（`ConditionReport`/`GovernanceAction`/`RISK_TIER`）+
P2（`execute_governance_action`/sinks），二者已落地（`4023e7d`/`ec8cf0d`）。**不依赖语料**，
单测用合成 `ConditionReport` + Mock LLM（与现有 `test_llm_controller` 同套路），可立即开工。
对应：`Q3_ACTION_GOVERNANCE_DESIGN.md` §4（双控制器）/ §5（validator）/ §6（治理执行流）。
负责人：Codex（代码 + 单测）。Claude 不写代码。

------

## 0. 架构定位与边界

```text
数据流（本 SPEC 补齐"动→治"两步，连通 P1/P2）：
  final pass_result → [P1 detect_conditions] → ConditionReport
    → [P4 controller.select]      提议 GovernanceProposal（rule / llm）
    → [P3 validate_governance]    白名单/合法性/风险表/前置门/越权/预算 → ok 或 forced_action
    → [P3 governor 路由]          auto→执行 / approval→pending / terminal→escalate
    → [P2 execute_governance_action] 落 sink + trace
```

**镜像 Q2 既有结构**（不要另发明体例）：P4 控制器照搬 `app/agent/controller.py` +
`llm_controller.py` 的 `RuleController/LLMController/build_prompt/safe_json_loads/_fallback`
模式；P3 validator 照搬 `app/agent/validator.py` 的 `validate()` + `ActionBudget` 模式。

边界：本 SPEC **不做** 动作级指标/归因/pass^k（P6）、对比 run（P7）、Web 控制台（P8）、
语料/gold（P5）。人审 commit 流只交付 **函数接口**（P8 控制台接它），eval 不依赖真人审。

------

## 1. P3：动作 validator + 风险路由 + 人审流（`app/govern/validator.py` + `governor.py`）

### 1.1 condition → 合法动作表（代码常量，`conditions.py` 或 `validator.py`）

```python
LEGAL_ACTIONS: dict[OpsCondition, list[GovernanceAction]] = {
    OpsCondition.stale_procedure:        [GovernanceAction.flag_stale,              GovernanceAction.escalate_to_human],
    OpsCondition.config_violation:       [GovernanceAction.open_remediation_ticket, GovernanceAction.escalate_to_human],
    OpsCondition.policy_violation:       [GovernanceAction.open_remediation_ticket, GovernanceAction.escalate_to_human],
    OpsCondition.missing_prereq:         [GovernanceAction.open_remediation_ticket, GovernanceAction.escalate_to_human],
    OpsCondition.broken_xref:            [GovernanceAction.open_remediation_ticket, GovernanceAction.escalate_to_human],
    OpsCondition.active_active_conflict: [GovernanceAction.send_alert,              GovernanceAction.escalate_to_human],
    OpsCondition.permission_blocked:     [GovernanceAction.escalate_to_human],   # 唯一合法
    OpsCondition.insufficient_evidence:  [GovernanceAction.escalate_to_human],
}
# escalate_to_human 永远合法（终结兜底）；no_op 仅当 conditions == []。
```

### 1.2 validator 签名与约束（`app/govern/validator.py`）

```python
class GovernanceProposal(BaseModel):   # 镜像 ActionProposal
    action: GovernanceAction
    args: dict[str, Any] = Field(default_factory=dict)
    source: str = "rule"
    reason: str | None = None
    controller_source: str | None = None
    llm_raw_proposal: dict[str, Any] | None = None
    accepted: bool = True
    fallback_reason: str | None = None

class GovernanceBudget(BaseModel):
    max_actions: int = Field(default=3, ge=0, le=3)
    consumed: int = Field(default=0, ge=0)

class GovValidationResult(BaseModel):
    ok: bool
    reject_reason: str | None = None
    forced_action: GovernanceAction | None = None   # 拒绝时强制降级目标（恒为 escalate_to_human）

def validate_governance(
    proposal: GovernanceProposal,
    report: ConditionReport,
    budget: GovernanceBudget,
) -> GovValidationResult: ...
```

约束（**承重墙；任一失败 → reject + `forced_action=escalate_to_human` + trace**）：

```text
1. 白名单：proposal.action ∈ GovernanceAction（no_op 不走 validator，见 §1.4）。
2. 合法性：若 conditions 非空，action 必须 ∈ ⋃ LEGAL_ACTIONS[c]（escalate 恒合法）。
3. 风险层：risk = RISK_TIER[action]（代码表）。忽略 proposal/llm 自报的任何风险字段。
4. 前置门（evidence）：action ∉ {escalate_to_human} 时要求 report.evidence_decision=="sufficient"，
   否则强制 escalate（防 F11：无证据执行副作用）。
5. 授权（越权）：RISK_TIER[action]∈{auto,approval} 时要求 report.authorized_actor==True，
   否则强制 escalate（防 F13：越权执行）。PERMISSION_BLOCKED 下唯一合法是 escalate。
6. 预算：budget.consumed < budget.max_actions，否则 reject。
7. 非法提议：以上任一不过 → ok=False + forced_action=escalate_to_human + 明确 reject_reason。
```

> 不变式：validator 失败时绝不放行副作用；被拒动作**一律降级为 escalate**（fail-closed），
> 不是静默丢弃。F11/F13 在此被代码堵死（=0 是 Q3 Gate 硬验收）。

### 1.3 风险路由 + 人审流（`app/govern/governor.py`）

```python
@dataclass
class GovernanceOutcome:
    proposal: GovernanceProposal
    validation: GovValidationResult
    record: ActionRecord | None      # no_op 时为 None
    trace: dict[str, Any]

def govern(
    report: ConditionReport,
    pass_result: RetrievalPassResult,
    actor: ActorContext,
    controller,                      # P4：rule 或 llm
    sink: ActionSink,
    *, budget: GovernanceBudget = GovernanceBudget(),
) -> GovernanceOutcome:
    """detect 已在上游完成。流程：
       conditions==[] → no_op（不调 sink，trace 记 no_op）。
       否则 controller.select(report) → validate_governance →
         ok=False → 用 forced_action 重组 proposal（escalate）→ execute（escalated）。
         ok=True  → 按 RISK_TIER 路由：
                    auto     → execute_governance_action → committed
                    approval → execute_governance_action → pending_approval（副作用未生效）
                    terminal → execute_governance_action → escalated
       trace 字段：conditions / proposed_action / controller_source / risk_tier /
                   validator_verdict / forced / approval_state / sink_record_id。"""
```

人审 commit 流（**仅交付接口，eval 不依赖；P8 控制台接**，`app/govern/approvals.py`）：

```python
def list_pending(sink: ActionSink) -> list[ActionRecord]: ...
def approve_pending(record_id: str, sink: ActionSink) -> ActionRecord:  # pending_approval → committed
def reject_pending(record_id: str, sink: ActionSink) -> ActionRecord:   # pending_approval → dropped
```

### 1.4 P3 单测矩阵

```text
test_legal_action_passes                  config_violation + open_ticket（授权,充分）→ ok
test_illegal_action_forced_escalate       stale_procedure + send_alert → reject + forced=escalate
test_unauthorized_forced_escalate         authorized_actor=False + open_ticket → reject + forced=escalate (F13)
test_insufficient_evidence_forced_escalate evidence=insufficient + flag_stale → reject + forced=escalate (F11)
test_permission_blocked_only_escalate      PERMISSION_BLOCKED：仅 escalate 合法
test_budget_exhausted_rejects             consumed==max → reject
test_risk_tier_from_table_not_proposal    proposal 自带 risk 字段被忽略，按 RISK_TIER
test_govern_no_op_when_no_condition        conditions==[] → no_op, record=None
test_govern_auto_commits                   flag_stale 授权充分 → committed + sink 一行
test_govern_approval_pending               open_ticket → pending_approval（未 committed）
test_govern_terminal_escalates             PERMISSION_BLOCKED → escalated
test_approve_pending_commits               pending → committed
test_reject_pending_drops                  pending → dropped
```

------

## 2. P4：双控制器（治理动作选择，`app/govern/controller.py` + `llm_controller.py`）

### 2.1 规则控制器（镜像 `app/agent/controller.py`）

```python
class GovernanceRuleController:
    controller_source = "rule"
    def select(self, report: ConditionReport, context=None) -> GovernanceProposal: ...
```

选择优先级（多条件 = 消融决策点，沿用 Q2 §3.1 承重设计）：

```text
1. conditions == []                         → no_op
2. PERMISSION_BLOCKED 或 authorized_actor=False → escalate_to_human   （越权优先终结）
3. INSUFFICIENT_EVIDENCE                     → escalate_to_human
4. ACTIVE_ACTIVE_CONFLICT                    → send_alert
5. CONFIG_VIOLATION/POLICY_VIOLATION/MISSING_PREREQ/BROKEN_XREF → open_remediation_ticket
6. STALE_PROCEDURE                           → flag_stale
7. 其余                                       → escalate_to_human（兜底）
```

`args` 装配（确定性，来自 report 信号）：ticket/alert 带 `doc_ids` + `evidence_citations`
（context-only，来自 pass_result）；flag_stale 带 `stale_doc_ids`；escalate 带 `reason`。

### 2.2 LLM 控制器（镜像 `app/agent/llm_controller.py`）

```python
class GovernanceLLMController:
    controller_source = "llm"
    def __init__(self, llm_client: BaseLLMClient, *, fallback=None):
        self.fallback = fallback or GovernanceRuleController()
    def select(self, report, context) -> GovernanceProposal: ...
```

- `build_governance_prompt(report, context)`：列出该 report 的 conditions、`LEGAL_ACTIONS` 并集、
  signals（doc_ids/conflict/authorized/evidence_decision），要求返回
  `{"action":"<∈ LEGAL_ACTIONS>","args":{...},"reason":"<=1句"}`。
  **明确禁令**：action 必须 ∈ LEGAL_ACTIONS；**不得输出/不会被采信任何 risk 字段**
  （风险层由代码表定）；citations 必须来自 NEIGHBORHOOD 给定的 chunk ids。
- 复用 `safe_json_loads` + `_generate_temperature_zero`（temperature=0）。
- parse 失败 / 非法 action / 非 dict args → `_fallback` 退化为 rule 版，标
  `source="llm_fallback_rule"`、`accepted=False`、`fallback_reason`。
- **关键**：LLM 提议即便合法也仍须过 §1.2 validator（越权/无证据照样被强制 escalate）——
  controller 选动作，validator 才是承重墙。

### 2.3 P4 单测矩阵

```text
test_rule_no_op_when_clean                 conditions==[] → no_op
test_rule_conflict_to_alert                ACTIVE_ACTIVE_CONFLICT → send_alert
test_rule_config_to_ticket                 CONFIG_VIOLATION → open_remediation_ticket
test_rule_stale_to_flag                    STALE_PROCEDURE → flag_stale
test_rule_unauthorized_to_escalate         authorized_actor=False → escalate
test_rule_multi_condition_priority         permission_blocked + stale 同在 → escalate（越权优先）
test_rule_args_citations_context_only      ticket/alert 的 citations ⊆ pass_result chunk ids
test_llm_valid_proposal_accepted           Mock LLM 合法 JSON → 采纳
test_llm_parse_error_falls_back            坏 JSON → fallback rule, accepted=False
test_llm_illegal_action_falls_back         action ∉ LEGAL → fallback
test_llm_cannot_self_downgrade_risk        LLM 自带 risk=auto，仍按 RISK_TIER 走 approval/validator
test_llm_unauthorized_still_escalated      LLM 提 ticket 但越权 → validator 强制 escalate（端到端）
```

------

## 3. 验收标准（P3 + P4）

```text
[ ] app/govern/validator.py：LEGAL_ACTIONS + validate_governance + GovernanceBudget；§1.4 单测全过
[ ] app/govern/governor.py：govern() 路由 auto/approval/terminal + no_op；trace 字段齐
[ ] app/govern/approvals.py：list/approve/reject_pending 接口（P8 用）
[ ] app/govern/controller.py + llm_controller.py：rule + llm 双控制器；§2.3 单测全过
[ ] 不变式实测：F11（无证据执行）=0、F13（越权执行）=0 —— 由 forced-escalate 测试覆盖
[ ] 风险层恒取自 RISK_TIER；validator/governor/controller 均不读 LLM 自报风险
[ ] LLM 控制器单测用 Mock LLM（不打真实 API）；无语料依赖
[ ] ruff 干净；pytest 全绿；app/agent/* 的 Q2 回归不变
```

非目标（后续）：动作级指标/归因/pass^k（P6）、对比 run（P7）、Web 控制台（P8）、语料+gold（P5 overlay/gold 段）。
