# P3-01~04 实现规格：Agent 骨架（诊断 → 规则 controller → 动作 → 重门 → 停止）

交给：Codex。出规格：Claude（已核 query_rewriter / hybrid_retriever filters /
real_pipeline Q1 loop 的接入点）。权威设计：`docs/Q2_AGENT_DESIGN.md`（freeze-ready）。

## 0. 范围边界（严格）

本规格只做 **P3-01~04 骨架 + 规则 controller**，产出新系统 `final_agentic_v2`
（controller=rule）。**不做**：LLM controller（P3-05）、逐动作归因 metrics（P3-06）、
eval run（P3-09）、pass^k（P3-10）。Q1 的 `final_agentic` 保持不动，`final_agentic_v2`
是并列新系统。骨架全程**零 LLM**可测（动作 a 是规则改写、b 是检索、controller 确定性；
答案生成沿用既有，测试用 mock）。

新包：`app/agent/`。

------

## P3-01：诊断提取器 `app/agent/diagnosis.py`

`diagnose(pass_result) -> DiagnosisReport`，纯规则、无 LLM。输入是一次 trust pass 的
结果（沿用 `app/workflow/state.py:RetrievalPassResult` + gate 输出）。

```python
class DiagnosisReport(BaseModel):
    evidence_decision: Literal["sufficient","insufficient"]
    permission_blocked_count: int      # 被 ACL 拦截的 chunk 数
    deprecated_neighbor_count: int     # 邻域 deprecated chunk 数
    restricted_neighbor_count: int     # 邻域 restricted chunk 数
    conflict_group_ids: list[str]      # 检出的 active-active 冲突组
    clean_active_count: int            # 干净可用证据 chunk 数
    top_rerank_score: float | None
    support_chunk_count: int
    entity_miss: bool                  # query 实体未命中
    failure_type: FailureType          # 描述性标签（主信号）
    legal_actions: list[ActionType]    # 权威：validator 据此执法（§3.1 并集）
```

**信号 → legal_actions 派生（§3 + §3.1，阈值用 W7 占位默认，注释标 TODO-W7）：**

```text
permission_blocked_count > 0 且 clean_active_count < min_support   → PERMISSION_BLOCKED, legal={e}
≥2 个 active chunk 同 conflict_group_id                            → CONFLICT, legal={d,e}
signal_policy_crowding = (deprecated+restricted) ≥ 2 且 clean < min_support  → b 合法
signal_weak_recall = (top_rerank_score < min_score) 或 entity_miss          → a 合法
  两 signal 同时 → legal={a,b,e}（§3.1 共现决策点）
  仅 policy_crowding → POLICY_CROWDING, legal={b,e}
  仅 weak_recall    → WEAK_RECALL, legal={a,e}
其余                                                              → NO_RECOVERY, legal={e}
```

优先级（决定 failure_type 标签）：PERMISSION_BLOCKED > CONFLICT > （policy_crowding /
weak_recall 共现或单发）> NO_RECOVERY。**permission/conflict 一旦命中即终结类，不进恢复。**

单测：每个 failure_type 一条；共现 case 产出 legal={a,b,e}；evidence_decision=sufficient
时不产恢复动作。

------

## P3-02：动作 `app/agent/actions.py`（动作 a 复用、b 新建，c 已砍）

统一接口：

```python
class ActionProposal(BaseModel):
    action: ActionType   # a=rewrite_query | b=filtered_retrieval | d=present_conflict_set | e=refuse_with_explanation
    args: dict           # a:{rewritten_query} b:{filters} d:{conflict_doc_ids} e:{reason}
    source: str          # "rule" | "llm"（本阶段只 rule）

def execute_action(proposal, query, retriever, reranker, settings) -> ActionResult
```

- **a rewrite_query**：复用 `app/retrieval/query_rewriter.rewrite_query_for_evidence`。
  不变式：rewritten 实体 ⊆ query ∪ 检索摘要实体（规则校验，见 validator V5）。
- **b filtered_retrieval（新）**：用 `HybridRetriever.retrieve(query, options, filters=...)`
  （filters 已支持）。filters **只收紧**：白名单字段 `status`(限 active)、
  `exclude_doc_ids`；**严禁** 放宽 access_level/role（validator V4 拦）。
- **d present_conflict_set**：列出 conflict 双方 doc_id + citation（沿用 Q1 report_conflict 逻辑）。
- **e refuse_with_explanation**：终结，带 reason。
- 检索类动作（a/b）执行后，**结果必须重过全部 gates**（state→ACL→evidence），与 Q1 二次检索一致。

单测：b 的 filters 不能让 restricted 重新进入（构造 restricted 邻居 → 过滤后仍不可见）；
a 的实体约束生效。

------

## P3-03：规则 controller + validator `app/agent/controller.py` / `app/agent/validator.py`

**RuleController.select(diagnosis) -> ActionProposal**（确定性查表）：

```text
PERMISSION_BLOCKED → e
CONFLICT           → d
legal 含 b 和 a（共现）→ 按优先序 b > a（默认，TODO-W7 可调）
legal 仅 b → b ; 仅 a → a
否则 → e
```

**Validator（§5，代码强制，不可关）`validate(proposal, diagnosis, budget) -> Ok|Reject`：**

```text
V1 proposal.action ∈ diagnosis.legal_actions
V2 非终结动作预算 ≤2
V3 PERMISSION_BLOCKED 下只接受 e
V4 b.filters 只收紧（白名单字段 + 方向校验；放宽 ACL/state → Reject）
V5 a.rewritten 实体 ⊆ 允许集
V6 检索类动作后强制重过 gates（由 orchestrator 保证调用）
V7 非法提议 → Reject + trace 记录 + fallback（llm→rule 选择；rule 不会非法，
   若 rule 自身越界视为 bug，Reject 并终结为 e）
```

单测：规则 controller 各分支；共现下选 b（默认优先）；validator 拒非法（如提议 b 但
legal={a,e}）；filters 放宽被拒。

------

## P3-04：orchestrator 集成 + trace `app/agent/loop.py`（或扩展 orchestrator）

把 Q1 的"单次 rewrite"loop 泛化为 **诊断 → controller → validator → execute → 重门 → 停止**：

```text
first_pass = trust_pass(query)            # 复用现有
loop (budget: 非终结动作 ≤2, 步数 ≤3):
    diag = diagnose(current_pass)
    if diag.evidence_decision == sufficient: break → answer
    proposal = controller.select(diag)
    if not validator.validate(proposal, diag, budget): → 终结 e
    if proposal.action ∈ {d,e}: → 终结（conflict-set / refuse）
    result = execute_action(proposal, ...)   # a/b
    current_pass = re-gate(result)           # 强制重门
    budget.consume()
答案生成/citation 沿用既有 final pipeline
```

**停止不变式（§6）**：必终结于 answer/refuse/conflict-set；无循环；
**同一动作类型同轨迹内不重复**（防 a-a / b-b）；预算耗尽 → e。

**trace 新字段**（每条 query）：

```text
agent_version: "v2"
controller_source: "rule"
action_trajectory: [ {step, diagnosis_failure_type, legal_actions,
                      chosen_action, action_source, validator_ok,
                      validator_reject_reason?, post_action_evidence_decision} ]
budget_consumed: int
terminal_reason: "answer" | "refuse" | "conflict_set" | "budget_exhausted"
```

接入 baselines：新增系统名 `final_agentic_v2`（controller=rule），不动 `final_agentic`。

单测：共现 case 走 b 后 evidence 充足 → answer；预算耗尽 → e；validator 拒绝被 trace；
无限循环不可能（同类型不重复 + 预算）；trace 字段齐全。

------

## 验收

```text
1. app/agent/ 四模块 + loop；final_agentic_v2 可在 runner 选中（mock 路径可跑通，零 token）。
2. 全部单测绿（diagnosis 各分支 + 共现、actions a/b 不变式、controller 查表、
   validator V1–V7、loop 停止不变式 + trace 字段）；不破坏既有 172 测试。
3. ruff 通过。
4. Q1 final_agentic 行为不变（回归测试）。
5. 不调 LLM controller、不做归因 metrics、不跑真实 eval——留给 P3-05/06/09。
```

## W7 留待确认（占位默认，注释标 TODO-W7，不阻塞骨架）

- min_support / min_score / policy-crowding 阈值的具体值（Phase 1 校准数据定）；
- 共现优先序默认 b > a；
- §9.6 二次检索合并语义（替换 vs 并集）——以 Q1 orchestrator 现行实现为准，
  实现时核实并在 PR 说明。

## 不做

```text
- 不引入 LLM controller（P3-05）；controller 仅 rule。
- 不加 judge / 运行时 verifier（决议 B 已撤）。
- 不动 Q1 final_agentic、不动 headline 评分逻辑。
- 动作 c（version-scoped）不实现（C2-05 已砍）。
```
