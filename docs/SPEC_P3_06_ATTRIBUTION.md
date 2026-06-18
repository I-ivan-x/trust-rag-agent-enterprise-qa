# P3-06 实现规格：逐动作 trajectory 归因

交给：Codex。出规格：Claude（已核 `loop.py` 的 trajectory 字段名）。
设计：`Q2_AGENT_DESIGN.md` §8。前置：P3-01~05 已落地（rule + llm controller、trace 含
`action_trajectory`）。

## 0. 目标与范围

把 trace 里的 `action_trajectory` 变成**逐动作量化指标 + trajectory 失败分类**，
**单运行内**计算、**按动作**报告、**不混入总指标**。这是 Agent 支柱叙事的承重指标层。

**零 token**：只读已落盘 run 产物（traces + results），不调 LLM、不重跑。
**范围**：单运行的归因计算 + 测试。**不做**：rule-vs-llm 并排对比（两个 run 都有了才做，
P3-09）、真实 eval run（P3-09）、pass^k（P3-10）、counterfactual replay（见 TF1）。

模块：`app/eval/agent_attribution.py`，接入 runner summary（仅 `final_agentic_v2*` run）
+ 一个 report 段。

## 1. 输入（真实字段，勿臆造）

每个 `final_agentic_v2*` run：
- `traces.jsonl`：每 case 一条，含 `action_trajectory`（list of step row）+ `terminal_reason`
  + `budget_consumed`。step row 字段：`step / diagnosis_failure_type / legal_actions /
  controller_source / chosen_action / chosen_source / accepted / fallback_reason /
  validator_ok / validator_reject_reason / post_action_evidence_decision / reason`。
- `results.jsonl`：每 case 的 `grounded_correct`（按 case_id join）。

动作枚举：`rewrite_query`(a) / `filtered_retrieval`(b) / `present_conflict_set`(d) /
`refuse_with_explanation`(e)。

## 2. 逐动作指标（按动作 A 报告，定义精确到字段）

```text
trigger_count(A)   = Σ steps where A ∈ step.legal_actions
                     （诊断给过该动作机会的次数）
accept_count(A)    = Σ steps where step.chosen_action == A AND step.accepted == True
                     （被选且 validator 放行并执行）
success_count(A)   = Σ cases where 某 step 执行了 A
                     AND 该 step.post_action_evidence_decision == "sufficient"
                     AND 该 case 的 results.grounded_correct == True
                     （真恢复：证据转充足且最终 grounded）
false_recovery(A)  = Σ cases where 执行了 A
                     AND post_action_evidence_decision == "sufficient"
                     AND grounded_correct == False
                     （假恢复：看似有证据，最终 grounded 失败——最值钱的诚实指标）
ineffective(A)     = Σ steps where chosen_action == A 是检索类(a/b)
                     AND post_action_evidence_decision == "insufficient"
                     （执行了但证据没改善）
```

join 规则：trajectory step 属于某 case（trace.case_id）；success/false_recovery 看该
case 的最终 grounded。一条 case 有多个恢复步时，归到使 evidence 翻 sufficient 的那一步
（若多步，归最后一个翻转步）。

## 3. Controller 归因（消融的关键）

- 每个 run 的 controller 由系统名决定（`final_agentic_v2`=rule，`final_agentic_v2_llm`=llm）。
- llm run **额外报告**：
  ```text
  llm_propose_count        llm 提出动作的步数
  llm_accept_count         llm 提议被 validator 放行的步数（chosen_source=="llm"）
  llm_fallback_count       llm 提议被拒/解析失败退化的步数（chosen_source=="llm_fallback_rule"
                           或 fallback_reason 非空）
  llm_fallback_rate        llm_fallback_count / llm_propose_count
  ```
  这量化"LLM 控制器有多少次真在做有效决策 vs 退化成 rule"。

## 4. Trajectory 失败分类（TF1–4，§8）

```text
TF2 无效动作        ineffective(a)+ineffective(b) 的 case（执行检索动作但证据没改善）
TF3 validator 拒绝  Σ steps where accepted==False 或 fallback_reason startswith "validator_reject"
                    （仅 llm run 可能 >0）
TF4 预算耗尽仍不足  Σ cases where terminal_reason == "budget_exhausted"（或对应终态）
TF1 选错动作        **counterfactual，本阶段不自动判**：仅输出候选集——
                    case 最终未 grounded 且该 case 某 step 有未被选的合法恢复动作。
                    实际"另一动作会不会成功"需 replay，标记 requires_replay=true，
                    留给 P3-09 可选 replay。不得在 P3-06 自动记 TF1 命中。
```

## 5. 输出

- summary.json 增 `agent_attribution` 块：per-action 四指标 + ineffective + （llm run）
  fallback 统计 + TF2/3/4 计数 + TF1 候选集（带 requires_replay 标记）。
- report 段（`docs/` 或 summary 内）：per-action 表 + TF 表。**按动作分行，不给单一总分**。
- 诚实标注：n 小时只报计数不报率；false_recovery 单列强调；TF1 标"未自动判定"。

## 6. 测试（合成 trajectory，零 token）

```text
1. trigger/accept 计数：构造含 legal_actions / chosen_action / accepted 的合成 trajectory → 计数正确。
2. success vs false_recovery：sufficient+grounded → success；sufficient+not grounded → false_recovery（区分正确）。
3. ineffective：检索动作后 insufficient → 计入 ineffective + TF2。
4. TF3：accepted==False 的 step → 计入 TF3（llm run）。
5. TF4：terminal_reason==budget_exhausted → 计入 TF4。
6. TF1 候选：未 grounded + 有未选合法动作 → 进候选集且 requires_replay==true，不自动记命中。
7. controller 归因：llm run 的 fallback_rate 计算正确。
8. 非 agent run（Q1 final_agentic / 无 trajectory）→ 无 attribution，优雅跳过。
```

## 7. 验收

```text
- ruff + pytest tests/unit 全绿；新增测试零 token；不破坏既有 199。
- agent_attribution 进 final_agentic_v2* 的 summary；report 段 per-action + TF 表。
- false_recovery 单列；TF1 仅候选不自动判；llm fallback_rate 报告。
- 不跑真实 eval、不做 pass^k、不做 rule-vs-llm 并排（P3-09）。
```

## 8. 不做

```text
- 不 replay、不自动判 TF1 命中。
- 不引入 LLM、不改 loop/validator/动作空间。
- 不把 agent attribution 并入 headline grounded 指标（单独报告）。
```
