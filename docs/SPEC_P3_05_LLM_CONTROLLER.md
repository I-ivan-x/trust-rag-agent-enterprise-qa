# P3-05 实现规格：LLM Controller（决议 A 的另一臂）

交给：Codex。出规格：Claude（已核 `run_agentic_v2_loop(controller=...)` 插点、
`ActionProposal`、`validator.validate`）。设计：`Q2_AGENT_DESIGN.md` §4 / §9.2。

## 0. 目标与范围

骨架(P3-01~04)给了规则臂。P3-05 加 **LLM 臂**，让决议 A（双控制器消融）成立：
`final_agentic_v2_llm` vs `final_agentic_v2`(rule)，**同一动作空间、同一 validator、
同一 loop**，唯一变量是 controller。

**不做**：逐动作归因 metrics（P3-06）、eval run（P3-09）、pass^k（P3-10）。
本阶段单测全程 **MockLLM 零 token**；真实 dry-run 可选（~5–10 次 DeepSeek 调用）。

**核心安全前提（必须保持）**：LLM controller 的输出是**不可信**的；validator 是信任
边界；非法/解析失败 → **确定性 fallback 到 rule controller 的选择**。安全性绝不依赖 LLM。
骨架已测过 validator + fallback，这里复用，不重写。

## 1. Controller 接口统一

当前 `RuleController.select(diagnosis)` 只吃 diagnosis。LLM 需要更多上下文（query、邻域）。
统一接口为：

```python
class ControllerContext(BaseModel):
    query: str
    neighborhood: list[dict]   # top-k 检索邻居：{doc_id, title, status, access_level, rerank_score}

# 两个 controller 同签名
def select(self, diagnosis: DiagnosisReport, context: ControllerContext) -> ActionProposal
```

- `RuleController.select(diagnosis, context)`：忽略 context，行为不变（回归测试保证）。
- loop 在调用前用现有 pass_result 构造 context（query + 邻居摘要）。

## 2. `app/agent/llm_controller.py`

```python
class LLMController:
    def __init__(self, llm_client, *, fallback: RuleController | None = None): ...
    def select(self, diagnosis, context) -> ActionProposal:
        # 1. build_prompt(diagnosis.legal_actions, signals, context)
        # 2. raw = llm_client.generate(prompt)   # DeepSeek 主模型, temperature=0
        # 3. parse {action, args, reason}
        # 4. 解析失败 / action ∉ legal_actions → fallback.select(...) ，source 标记
        # 5. 成功 → ActionProposal(action, args, source="llm", reason=...)
```

**模型**：系统主模型（DeepSeek），`temperature=0`，结构化输出。
**无需二次家族 guard**——controller 是"选动作"，不评判自己的答案，无 self-preference
（§9.2 已裁定，别照搬 judge 的家族 guard）。

**prompt（草案，Codex 落地可微调，与 output parser 同步）：**

```text
You choose exactly ONE recovery action for a retrieval-augmented QA system that
found INSUFFICIENT evidence. You may ONLY choose from LEGAL_ACTIONS. You cannot
bypass access-control or document-state controls; filters may only narrow.

QUERY: {query}
FAILURE_TYPE: {failure_type}
LEGAL_ACTIONS: {legal_actions}     # 你只能从这里选
SIGNALS: deprecated_neighbors={..}, restricted_neighbors={..},
         clean_active={..}, top_rerank_score={..}, entity_miss={..}
NEIGHBORHOOD (top retrieved):
  - {doc_id} | {title} | status={..} | access={..} | score={..}
  ...

Return JSON only:
{"action": "<one of LEGAL_ACTIONS>",
 "args": { ... },          // rewrite_query:{rewritten_query}; filtered_retrieval:{filters:{status?,exclude_doc_ids?}}; present_conflict_set:{conflict_group_ids}; refuse_with_explanation:{reason}
 "reason": "<= 1 sentence"}

Rules: action MUST be in LEGAL_ACTIONS. filtered_retrieval filters may only
tighten (status=active and/or exclude_doc_ids drawn from NEIGHBORHOOD).
rewrite_query must not introduce entities absent from QUERY or NEIGHBORHOOD.
```

解析 fallback：JSON 失败、缺字段、action 非法 → 记 warning + fallback 到 rule。

## 3. loop 的 reject-fallback（关键改动）

骨架 loop 现在 validator reject → 终结 e（因 rule 不会非法）。P3-05 后，LLM **可能**提出
被 validator 拒的动作。改 loop：

```text
proposal = controller.select(diagnosis, context)
vr = validator.validate(proposal, diagnosis, budget)
if not vr.ok:
    if proposal.source == "llm":
        proposal = rule_controller.select(diagnosis, context)   # 确定性 fallback
        vr = validator.validate(proposal, diagnosis, budget)
        record fallback_reason = "validator_reject:" + vr.reason（原 LLM 拒因）
    if not vr.ok:   # rule 仍非法（视为 bug）→ 终结 e
        terminate(e)
```

即：**LLM 被拒 → 退化为 rule 的选择**，而非直接拒答。这正是"安全不依赖 LLM"的运行时体现。

## 4. 系统接入

- 新系统名 `final_agentic_v2_llm`（runner/baselines 可选中）。`final_agentic_v2` 仍是 rule 变体。
- `real_pipeline.py`：`final_agentic_v2_llm` → `run_agentic_v2_loop(controller=LLMController(client, fallback=RuleController()))`。
- 选 llm 变体时才构造 LLM client；rule 变体零 LLM 不变。

## 5. trace（为 P3-06 归因铺路）

每个 controller 决策步记录：

```text
controller_source: "rule" | "llm"
llm_raw_proposal: {action, args, reason} | null      # LLM 原始提议（含被拒的）
accepted: bool
fallback_reason: "parse_error" | "validator_reject:<reason>" | null
chosen_action / chosen_source: 最终执行的动作及其来源（llm 或 llm_fallback_rule）
reason: LLM 的 reason 文本（若有）
```

## 6. 测试（MockLLM，零 token）

```text
1. MockLLM 返回合法动作 → accepted，trace source=llm。
2. MockLLM 返回非法动作（∉ legal_actions）→ validator 拒 → fallback rule，trace fallback_reason。
3. MockLLM 返回坏 JSON → 解析 fallback → rule。
4. MockLLM 提议 filter 放宽 → validator V4 拒 → fallback。
5. MockLLM 提议 rewrite 加新实体 → validator V5 拒 → fallback。
6. **安全保证测试**：MockLLM 永远返回非法 → final_agentic_v2_llm 行为 == rule 变体
   （逐步 chosen_action 一致）。这是"最坏情况退化为 rule"的硬证明。
7. temperature=0 传入 LLM 调用（断言）。
8. final_agentic_v2_llm 可经 mock runner 选中、零 token 跑通。
9. RuleController + Q1 final_agentic 行为不变（回归）。
```

## 7. 验收

```text
- ruff + pytest tests/unit 全绿（新增 LLM controller 测试均 MockLLM 零 token）；不破坏既有 190。
- final_agentic_v2_llm 可选中；rule 变体与 Q1 不变。
- LLM 提议走同一 validator；被拒/解析失败 → 确定性 fallback 到 rule，且 trace 记录。
- 无二次家族 guard（controller ≠ judge）。
- 可选：~5–10 次 DeepSeek dry-run 确认真实解析，日志留存，不进 CI。
```

## 8. 不做

```text
- 不做逐动作归因 metrics（P3-06）、不跑真实 eval（P3-09）、不做 pass^k（P3-10）。
- 不改 validator 规则、不改动作空间、不动 headline 评分。
- LLM 仅做 controller；不把 LLM 引入 validator 或 gate。
```
```
