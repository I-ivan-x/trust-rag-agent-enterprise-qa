# SPEC Q3-P1 + P2：条件检测器 + 本地 MCP server / sink

版本：v1-q3-p1p2-impl
状态：实现规格（freeze-ready）。可与 P5 语料抓取**并行**——P1/P2 不依赖语料，单测用合成
`RetrievalPassResult` fixture（与现有 `tests/.../test_diagnosis.py` 同套路）。
对应：`Q3_ACTION_GOVERNANCE_DESIGN.md` §3（诊断→条件）/ §5（validator 前瞻）/ §7（MCP）。
负责人：Codex（代码 + 单测）。Claude 不写代码，散文/报告归 Claude。

------

## 0. 架构定位（务必先读：Q3 是新层，不动 Q2）

```text
现有 Q2 检索恢复 agent（app/agent/*）：动作 = rewrite/filter/conflict/refuse，恢复检索失败。
                                       —— 不改、不重载。
Q3 动作治理层（新建 app/govern/*）：消费 Q2 产出的最终 RetrievalPassResult + ActorContext，
                                  检出 ops 条件 → 提议治理动作（有副作用）→（P3 路由/校验）→
                                  经 sink/MCP 落地 → trace。

数据流：retrieve + 四道 gate (+Q2 恢复) → final pass_result
        → [P1] detect_conditions → ConditionReport
        → [P4] controller 选动作（本 SPEC 不含）
        → [P3] validator + risk-tier 路由（本 SPEC 不含）
        → [P2] executor → MCP/sink 落 data/action_store/*.jsonl
```

**P1/P2 的边界（防蔓延）：**
- P1 只做 **条件检测**（纯规则，无 LLM，无动作选择）。
- P2 只做 **副作用机制**（sink + MCP server + executor）：给定一个"已校验、已批准"的动作，
  执行并记账。**不决定选哪个动作（P4），不做 gate 前置/风险路由（P3）。**
- 二者都 **不依赖语料**、**不调 LLM**、**不接生产外部系统**（ADR-014）。

------

## 1. P1：条件检测器（`app/govern/conditions.py`）

### 1.1 枚举与 schema

```python
class OpsCondition(StrEnum):
    stale_procedure        = "STALE_PROCEDURE"
    config_violation       = "CONFIG_VIOLATION"
    active_active_conflict = "ACTIVE_ACTIVE_CONFLICT"
    missing_prereq         = "MISSING_PREREQ"
    broken_xref            = "BROKEN_XREF"
    policy_violation       = "POLICY_VIOLATION"
    insufficient_evidence  = "INSUFFICIENT_EVIDENCE"
    permission_blocked     = "PERMISSION_BLOCKED"

class GovernanceAction(StrEnum):
    flag_stale              = "flag_stale"
    open_remediation_ticket = "open_remediation_ticket"
    send_alert              = "send_alert"
    escalate_to_human       = "escalate_to_human"
    no_op                   = "no_op"   # 终结结果，非 sink 动作

class RiskTier(StrEnum):
    auto = "auto"; approval = "approval"; terminal = "terminal"

# 代码表：动作→风险层。LLM 不得覆盖（P3 validator 强制读这张表，不读 LLM 自报）。
RISK_TIER: dict[GovernanceAction, RiskTier] = {
    GovernanceAction.flag_stale:              RiskTier.auto,
    GovernanceAction.open_remediation_ticket: RiskTier.approval,
    GovernanceAction.send_alert:              RiskTier.approval,
    GovernanceAction.escalate_to_human:       RiskTier.terminal,
}

class ConditionReport(BaseModel):
    conditions: list[OpsCondition] = Field(default_factory=list)
    authorized_actor: bool
    evidence_decision: Literal["sufficient", "insufficient"]
    # 归因/trace 用的信号明细（沿用 diagnosis.py 的累计风格）
    stale_doc_ids: list[str] = Field(default_factory=list)
    violating_doc_ids: list[str] = Field(default_factory=list)
    conflict_group_ids: list[str] = Field(default_factory=list)
    broken_xref_doc_ids: list[str] = Field(default_factory=list)
    permission_blocked_count: int = Field(ge=0, default=0)
```

### 1.2 入口签名

```python
@dataclass(frozen=True)
class ActorContext:
    role: str                     # admin | editor | viewer（沿用 gold 的 user_role）
    clearance: str | None = "internal"
    department: str | None = None
    requested_action: GovernanceAction | None = None  # 用户显式请求的动作（越权判定用）

def detect_conditions(
    pass_result: RetrievalPassResult,
    actor: ActorContext,
    *,
    authorized_roles: Mapping[GovernanceAction, frozenset[str]] = DEFAULT_AUTHORIZED_ROLES,
) -> ConditionReport: ...
```

`DEFAULT_AUTHORIZED_ROLES`（代码默认，可被调用方覆盖）：

```text
flag_stale:              {admin, editor}
open_remediation_ticket: {admin, editor}
send_alert:              {admin}
escalate_to_human:       {admin, editor, viewer}   # 谁都能升级
# viewer 不在 ticket/alert 授权集 → 越权 → PERMISSION_BLOCKED
```

### 1.3 检测规则（纯规则；复用现有 gate 信号）

复用 `diagnosis.py` 已有的访问器，**不要重新发明**：
`pass_result.acl_decision.blocked_chunks` / `state_decision.deprecated_chunks` /
`conflict_decision` / `evidence_decision`，以及 `_conflict_group_ids(pass_result)` 同款逻辑。

| condition | 检测规则（信号来源） |
| --- | --- |
| `PERMISSION_BLOCKED` | `acl_decision.blocked_chunks` 非空 **或** `actor.requested_action` 存在且 `actor.role ∉ authorized_roles[requested_action]`（越权） |
| `ACTIVE_ACTIVE_CONFLICT` | 复用 `_conflict_group_ids(pass_result)` —— 两篇 `status=active` 同 `conflict_group_id` |
| `STALE_PROCEDURE` | top-k 中存在 `chunk.status==deprecated` 且其 doc 有 `superseded_by`（来自 overlay 元数据） |
| `BROKEN_XREF` / `MISSING_PREREQ` | retrieved 文档的 `overlay_relation_note` 指向一个 `status∈{deprecated, missing}` 的 xref 目标 |
| `CONFIG_VIOLATION` / `POLICY_VIOLATION` | retrieved 文档带 `policy_ref` 且与某 `policy-` 文档的约束冲突（见 §1.4 元数据契约） |
| `INSUFFICIENT_EVIDENCE` | `evidence_decision == insufficient` 且无上述任何 actionable 条件 |
| （无 condition） | evidence sufficient 且未命中任何条件 → `conditions=[]`（对应 gold `no_op`） |

授权判定 `authorized_actor`：若 `actor.requested_action` 给定，则 = `role ∈ authorized_roles[that]`；
否则 = True（系统自发巡检、无特定请求动作）。

### 1.4 P1↔P5 元数据契约（让 P1 现在就能写、P5 来填）

P1 检测依赖以下 **chunk/doc 级元数据字段**；现有已有 `status / access_level / conflict_group_id`，
新增字段由 P5 overlay 填充。**若 `RetrievedChunk` 上暂无该字段，P1 从 doc 元数据透传适配
（实现注：加一个 `GovernanceSignals` 适配器抽取，不污染 RetrievedChunk）。**

```text
已有：status(active|deprecated) · access_level · conflict_group_id · doc_id
P5 新增（overlay）：
  superseded_by: str | None         # STALE_PROCEDURE
  overlay_relation_note: {type: "xref"|"violates_policy", target_doc_id, target_status}
  policy_ref: str | None            # 指向约束它的 policy- 文档
  metadata_origin: native | seeded_overlay
```

### 1.5 P1 单测矩阵（合成 fixture，无语料）

```text
test_detect_permission_blocked_from_acl        acl blocked → PERMISSION_BLOCKED
test_detect_permission_blocked_from_unauthorized viewer 请求 ticket → PERMISSION_BLOCKED + authorized_actor=False
test_detect_active_active_conflict             两 active 同 group → ACTIVE_ACTIVE_CONFLICT
test_detect_stale_procedure                    deprecated + superseded_by → STALE_PROCEDURE
test_detect_broken_xref                        relation_note 指向 deprecated → BROKEN_XREF
test_detect_config_violation                   policy_ref 冲突 → CONFIG_VIOLATION
test_detect_insufficient_evidence              insufficient + 无其他 → INSUFFICIENT_EVIDENCE
test_detect_no_condition_is_noop               sufficient + 干净 → conditions=[]
test_detect_multi_condition                    stale + conflict 同时 → 两者都在 list（控制器决策点）
test_authorized_roles_override                 自定义 authorized_roles 生效
```

------

## 2. P2：本地 MCP server + sink + executor（`app/govern/`）

### 2.1 模块布局

```text
app/govern/sinks.py        ActionSink 协议 + LocalJsonlSink（写 data/action_store/*.jsonl + 去重）
app/govern/mcp_server.py   本地 MCP server `runbook_ops_mcp`，4 个 tool 薄包装 sinks
app/govern/executor.py     ActionExecutor：已批准动作 → 调对应 sink → 返回 ActionRecord
data/action_store/         tickets.jsonl / alerts.jsonl / annotations.jsonl / escalations.jsonl
```

### 2.2 sink 记录 schema（统一）

```python
class ActionRecord(BaseModel):
    record_id: str                 # f"{action}-{8位hash}"，确定性可测
    action: GovernanceAction
    condition: OpsCondition | None
    doc_ids: list[str]
    evidence_citations: list[str]  # 来自 pass_result 的 context-only chunk ids（沿用 Q1 引用纪律）
    actor_role: str
    risk_tier: RiskTier
    approval_state: Literal["committed", "pending_approval", "escalated"]
    dedup_key: str                 # sha256(action|sorted(doc_ids)|condition)[:16]
    created_at: str                # ISO8601 UTC
```

### 2.3 sink 契约（语义不重叠，见设计 §2.1）

| MCP tool | sink 文件 | approval 默认 | 语义 |
| --- | --- | --- | --- |
| `create_ticket` | tickets.jsonl | pending_approval | 可追踪整改工单（待办） |
| `send_alert` | alerts.jsonl | pending_approval | **只读广播**：无指派、不开待办、不路由具体人 |
| `flag_document` | annotations.jsonl | committed | 只写标注元数据，不改正文；幂等 |
| `escalate` | escalations.jsonl | escalated | 路由决策点给人；fail-closed 出口 |

**去重/幂等（sink 层强制）**：同 `dedup_key` 已存在 → 不重复写，返回既有 `record_id`。
所有写 append-only，可回滚（删行即回滚），可审计。

### 2.4 MCP server 与 sink 解耦（关键测试性设计）

```text
sinks.py 是核心（纯函数式写 jsonl）；mcp_server.py 只是把 sink 暴露成 MCP stdio tool。
ActionExecutor 默认 in-process 直调 sinks（eval/单测确定性，不需 MCP transport）；
MCP server 仅用于"真工具调用"的 demo 形态（复活 Q2 被砍的 D 动作）。
→ 单测不依赖 MCP 运行时；demo 时起 server 走 stdio。
依赖：用官方 `mcp` Python 包（modelcontextprotocol）做 stdio server；若未引入，加进 pyproject 可选组。
```

### 2.5 executor 签名

```python
def execute_governance_action(
    action: GovernanceAction,
    report: ConditionReport,
    pass_result: RetrievalPassResult,
    actor: ActorContext,
    sink: ActionSink,
) -> ActionRecord:
    """假设动作已通过 P3 validator + 已获批准。按 RISK_TIER 决定 approval_state：
       auto→committed 落 sink；approval→pending_approval 落 sink（标记待审，副作用未生效）；
       terminal→escalated 落 escalations。幂等去重。no_op 不调本函数。"""
```

> P2 的 executor **假设已校验/已批准**——真正的 gate 前置、风险路由、人审 commit 在 P3。
> P2 落 `pending_approval` 记录即视为"已提议未提交"，符合设计 §2.1 的 proposed/committed 记账。

### 2.6 P2 单测矩阵

```text
test_create_ticket_writes_record          tickets.jsonl 一行，字段齐
test_send_alert_is_broadcast_only         alerts 记录无 assignee/owner 字段
test_flag_document_committed              annotations approval_state=committed
test_escalate_writes_escalation           escalations.jsonl，approval_state=escalated
test_dedup_idempotent                     同 dedup_key 二次调用不新增行、返回同 record_id
test_executor_risk_tier_mapping           flag→committed / ticket,alert→pending_approval / escalate→escalated
test_mcp_server_tool_roundtrip            in-process 起 server，调 create_ticket，sink 落盘一致
test_evidence_citations_context_only      citations ⊆ pass_result 的 chunk ids（越界即报错）
```

------

## 3. 验收标准（P1 + P2）

```text
[ ] app/govern/conditions.py：OpsCondition/GovernanceAction/RiskTier/RISK_TIER/ConditionReport/
    detect_conditions 落地；§1.5 单测全过
[ ] app/govern/sinks.py + executor.py + mcp_server.py：§2.6 单测全过
[ ] data/action_store/ 四 sink 可写、去重幂等、append-only 可回滚
[ ] 无 LLM 调用、无语料依赖、无外部系统写（grep 自查）
[ ] ruff 干净；pytest 绿；不改 app/agent/* 既有 Q2 行为（回归绿）
[ ] RISK_TIER 为代码常量；executor 不读任何"LLM 自报风险"字段
```

非目标（留给后续 P3/P4/P5，本 SPEC 不做）：动作选择控制器、validator 前置门/风险路由强制、
人审 commit 流、LLM controller、语料/gold、Web 控制台。
