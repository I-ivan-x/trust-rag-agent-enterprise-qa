# SPEC Q5-P1/P2：评测合同隔离 + Authorized DecisionContext

版本：v1-q5-p1-p2
状态：implementation-ready
依赖：`Q5_P0_DIAGNOSTIC.md`、`Q5_ADAPTIVE_AGENT_DESIGN.md` §6/§8/§10
执行窗口：implementation
解释权/验收：plan/report

------

## 0. 本批目标

本批不实现 multi-turn Agent。它只建立两个后续不可逆基础：

1. runtime task 与 grader gold 物理隔离，彻底删除 gold→execution 路径；
2. controller 获得经过 ACL 过滤、可做语义判断但不会泄漏 restricted text 的 DecisionContext。

只有本批验收通过，P3/P4 才能开始。

------

## 1. P0 baseline hygiene（先做，独立 commit）

P1 前先恢复仓库的可发布基线：

- 修 `scripts/build_showcase_snapshots.py` 的 15 个 Ruff E501；
- 注册 pytest `realprovider` marker，清除 unknown mark warning；
- 不在本批顺带升级第三方依赖；
- 新增 `.github/workflows/ci.yml`：Python/uv、Ruff、pytest、frontend build、合成 release-gate fixture；
- release gate 不依赖 gitignored real run；
- `make lint`、`make test`、frontend build 全绿。

P0 不允许修改任何 Q1-Q4 指标、阈值、gold 或 validator。

------

## 2. P1 文件布局

新增，禁止复用旧 `EvalCase` 把 task 和 gold 塞在同一对象：

```text
app/schemas/q5_task.py
app/eval/q5_dataset.py
tests/unit/test_q5_dataset_contract.py

data/q5/dev/tasks.jsonl
data/q5/dev/environment.jsonl
data/q5/dev/gold.jsonl          # 由 plan/report 窗口后续编写；implementation 不创正式 gold
data/q5/dev/corpus/
data/q5/dev/manifest.json
```

implementation 可以在 `tests/fixtures/q5/` 创建最小合成 fixture，但不能编写承重 q5_dev/q5_test case。

------

## 3. Task / Gold Schema

### 3.1 `Q5TaskInput`（runtime 可读）

```text
case_id: str
query: str
actor:
  role: str
  clearance: str
  department: str | null
requested_capability: document_maintenance | remediation_management | incident_response | investigate
resource_refs: list[str]
available_tools: list[str]
corpus_namespace: str
environment_ref: str
max_observation_steps: int <= 2
max_terminal_actions: 1
```

`requested_capability` 是 scenario input，不是预测目标。它表示用户请求的能力边界，供 authorization 使用；
`investigate` 仅允许 read-only observation、`no_op` 或 `escalate_to_human`，不能直接 commit side effect。
禁止从 gold 回填。

### 3.2 `Q5EnvironmentState`（tool runtime 可读）

```text
environment_ref: str
policy_exceptions: map
change_states: map
incident_impacts: map
initial_records: list
tool_faults: optional map
```

环境状态只能通过工具 schema 暴露相应切片；controller 不得直接读取完整 state。

### 3.3 `Q5Gold`（grader only）

```text
case_id: str
stratum: deterministic | semantic | adversarial
allowed_terminal_actions: list[str]
forbidden_terminal_actions: list[str]
required_observations: list[str]
final_state_assertions: list[assertion]
gold_reason_tags: list[str]
authorized: bool
source_refs: list[str]
author: str
```

允许多个 action sequence，只要 final state assertions 全部成立。不要把单一 action string 当作全部 gold。

### 3.4 Runtime 禁止字段

以下字段若出现在 task/controller/trace payload，立即 fail：

```text
stratum
gold_*
allowed_terminal_actions
forbidden_terminal_actions
required_observations
final_state_assertions
authorized (gold label)
```

------

## 4. Dataset Loader Contract

`app/eval/q5_dataset.py` 至少提供：

```python
load_q5_tasks(path) -> list[Q5TaskInput]
load_q5_environment(path) -> Q5EnvironmentStore
load_q5_gold(path) -> dict[str, Q5Gold]
join_q5_results_with_gold(results, gold) -> grader rows
validate_q5_dataset(tasks, environment, gold=None) -> report
```

约束：

- runtime runner 只能接收 tasks/environment，不接受 gold 参数；
- gold join 发生在所有 trajectories 完成后；
- case_id 唯一；environment_ref 必须存在；
- task tool allowlist 必须是代码 whitelist 子集；
- dev/test namespace 不得混载；
- manifest 记录 task/gold/environment/corpus 各自 sha256；
- test loader 后续支持只给 runner tasks/environment，再由 grader 进程读 gold。

------

## 5. P2 DecisionContext

新增 `app/govern/q5_context.py`，不要改变 Q4 的 `GovernanceControllerContext`，避免历史行为漂移。

### 5.1 Schema

```text
Q5DecisionContext
  query
  actor_claims
  requested_capability
  conditions
  evidence_decision
  authorized_evidence[]
    chunk_id / doc_id / text_excerpt / status / section_path
    source_origin / rerank_score / relation_summary
  blocked_evidence_metadata[]
    opaque_chunk_id / block_reason
  observations[]
  legal_terminal_actions[]
  remaining_observation_budget
  remaining_terminal_budget
```

### 5.2 Evidence 构造

- `authorized_evidence` 只能来自 ACL surviving chunks；
- 不得从原始 `reranked_chunks` 直接复制正文，因为其中可能含 blocked 内容；
- excerpt 默认每 chunk ≤600 chars，总 authorized evidence ≤4,000 chars；
- 保留 chunk_id 以支持 citation binding；
- score/provenance/relation 只读；
- blocked metadata 使用不可逆 opaque id 或原 id，禁止 title/section/text；
- prompt 中不得包含整个 Pydantic object dump 的未审字段。

### 5.3 Prompt Contract

Q5 LLM prompt 只能要求结构化输出，不保存/要求 chain-of-thought：

```json
{
  "kind": "observe|terminal",
  "tool": "<read-only tool or null>",
  "args": {},
  "action": "<terminal action or null>",
  "evidence_chunk_ids": [],
  "reason_code": "short_enum",
  "reason_summary": "one sentence"
}
```

`reason_summary` 仅用于审计，不参与 gold scoring。

------

## 6. Requested Capability 修复

Q5 runner 禁止调用旧 `_requested_action(case)`。使用：

```text
Q5TaskInput.requested_capability
  -> server-side capability-to-actions mapping
  -> intersection(actor role actions, capability actions)
  -> per-terminal-proposal authorization
```

冻结 mapping：

```text
document_maintenance  -> flag_stale
remediation_management -> open_remediation_ticket
incident_response     -> send_alert
investigate           -> read-only observation + no_op/escalate only
```

authorization 对 read-only observation 和最终 side effect 分别判定。每个 terminal proposal 都必须根据
actor role 与 capability 重新计算授权，不能复用 initial `ConditionReport.authorized_actor=True`。Q5 可在调用
旧 validator 前构造 per-proposal report/capability verdict，但不得弱化旧 validator 的 evidence、risk 或
legal-action 约束。

旧 Q4 runner 保持不动，以保证 frozen result 可复现；新增单测明确 Q5 路径不会引用 `_requested_action`。

------

## 7. P1/P2 单测

必须覆盖：

```text
test_q5_runtime_loader_has_no_gold_parameter
test_q5_task_rejects_gold_only_fields
test_q5_gold_join_happens_after_results
test_q5_case_ids_and_environment_refs_validate
test_q5_manifest_hashes_task_gold_env_corpus_separately
test_q5_requested_capability_never_falls_back_to_gold
test_q5_terminal_proposal_reauthorizes_against_actor_and_capability
test_q5_investigate_cannot_commit_side_effect

test_q5_context_contains_authorized_text_and_scores
test_q5_context_never_contains_blocked_text_title_or_section
test_q5_context_excerpt_and_total_budget
test_q5_context_preserves_chunk_ids_for_citations
test_q5_prompt_output_schema_rejects_extra_risk_or_auth_fields
test_q5_trace_contains_no_gold_only_fields
```

承重测试：构造一个 restricted chunk，其正文含唯一 canary；遍历 context、prompt、trace 的 JSON 序列化文本，
断言 canary 完全不存在。

------

## 8. 验收

- [ ] P0 lint/test/frontend/CI workflow 全绿；
- [ ] Q1-Q4 364 passed 基线无回归，新增测试另计；
- [ ] Q5 task/gold/environment 三对象、三 loader；
- [ ] runtime API 无 gold 参数；
- [ ] 旧 `_requested_action` 不进入 Q5 path；
- [ ] authorized evidence 有正文，blocked evidence 零正文泄漏；
- [ ] Q4 context/controller/validator 行为不改；
- [ ] 无 real provider 调用，无 q5_test 文件。

完成后提交两个独立 commit：P0 hygiene、Q5-P1/P2 contract。然后停止，回报 plan/report 窗口审查。
