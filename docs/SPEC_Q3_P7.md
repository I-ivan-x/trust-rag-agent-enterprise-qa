# SPEC Q3-P7：治理对比 run（rule vs llm，k=3）+ 报告

版本：v1-q3-p7-impl
状态：实现规格（freeze-ready）。依赖 P1–P6 全部已落（`b6bf6df`/`f408a8b`/`4fee18c`）。
对应：`Q3_ACTION_GOVERNANCE_DESIGN.md` §8（评测）/ §10（F10–F13）/ Q3 Gate；`SPEC_Q3_P6.md` §1 行契约。
分工：Codex（run harness 代码 + 单测）/ Owner（真实 k=3 run + 产物备份）/ Claude（报告散文）。

------

## 0. 定位

```text
P7 = 把 P1–P6 接成端到端治理对比 run，产出真实 action-metric 读数 + 报告。
  Codex：治理 run path（govern_runner + 脚本）+ summary 接 P6 函数 + 动作 headline 合约。
  Owner：rule vs llm × k=3 真实 run（ops_runbook_action_v1，真实 embedding/rerank/LLM）。
  Claude：EVALUATION_REPORT Q3 节（三段式）+ FAILURE_ANALYSIS F10–F13 + 数字纪律。
```

镜像 Q2 先例 `scripts/run_p3_agent_ablation.py`（k=3、复用 `_run_case_real`、写
results/traces/summary）。治理是 pipeline **之后** 的层，故走专用脚本而非重载 `run_eval` 的 QA 路径。

------

## 1. 治理 run path（`app/eval/govern_runner.py` + `scripts/run_q3_governance_ablation.py`）

### 1.1 单 case 治理执行（可测，`app/eval/govern_runner.py`）

```python
def run_governance_case(
    case: EvalCase,
    controller,                 # GovernanceRuleController | GovernanceLLMController
    retriever, reranker, settings,
    *, system_name: str, run_index: int,
    evidence_gate_config=None,
) -> dict[str, Any]:
    """1. run_trust_gated_pass(query, user_role=case.user_role, ...) → final pass_result
       2. ActorContext(role=case.user_role, requested_action=_requested_action(case))
       3. report = detect_conditions(pass_result, actor)
       4. outcome = govern(report, pass_result, actor, controller, sink)
       5. 落 §1.2 行（含 P6↔P7 契约字段 + gold 透传）+ 对应 trace 行。"""
```

`_requested_action(case)`：从 gold/query 推断用户显式请求的动作（越权子集 ora-009/010/011
的 query 是"请求开工单/发告警"——映射到 `requested_action`，喂 P1 越权判定）。

### 1.2 result 行（必须满足 `SPEC_Q3_P6.md` §1 契约）

```text
身份：case_id · system_name · run_index · split
gold 透传：gold_action · gold_condition · secondary_conditions · authorized · expected_tier · gold_doc_ids
预测：detected_conditions · authorized_actor · evidence_decision · proposed_action ·
      controller_source · risk_tier · validator_ok · forced_action · approval_state ·
      executed_side_effect · sink_record_id
```

trace 行另存 govern() 的完整 `trace`（conditions/proposed/validator_verdict/forced/approval/sink_record）。

### 1.3 ablation 脚本（Owner 跑，`scripts/run_q3_governance_ablation.py`）

```text
SYSTEMS = ["final_governed_rule", "final_governed_llm"]   # 控制器二选一
DEFAULT_RUN_ID = "q3-p7-governance-ablation"
流程：rebuild_indexes(ops corpus, real embedding+bge rerank)
      → for system in SYSTEMS: for case in ops_runbook_action_v1: for run_index in range(k):
            run_governance_case(...) → 收集 result/trace 行
      → 写 results.jsonl / traces.jsonl / failures.jsonl
      → summary = compute_governance_metrics + compute_governance_attribution + compute_govern_passk(k)
      → 写 summary.json（含 §3 headline 合约字段）
参数：--k 3 · --real-run · --systems · --run-id；sink 用临时隔离目录（不污染 demo action_store）
```

------

## 2. run 协议（Owner）

```text
前置：启动 Docker/Qdrant（否则向量栈静默退化 keyword-only，run 作废）；
      check_eval_leakage.py 对 ops_runbook_action_v1 已通过（P5 验收项）。
命令：python -m uv run python scripts/run_q3_governance_ablation.py \
        --systems final_governed_rule,final_governed_llm --k 3 --real-run
预算：rule 系统 0 次 LLM 调用；llm 系统 14 case × 3 = 42 次（动作选择 prompt 短）≈ ¥1–2。
产物：q3-p7-governance-ablation/{results,traces,failures}.jsonl + summary.json；
      被报告引用 → 异地备份 summary + results（沿用 ROADMAP §8 风险预案）。
```

> 真实 embedding/rerank 必须真实（与 Week6 一致）；mock 产物不得进 headline（mock_used 合约）。

------

## 3. summary + 动作 headline 合约（`govern_runner` / 脚本）

```python
governance_headline_eligible = bool(
    real_run and not mock_used
    and per_system["anti_gaming_triad_ok"]
    and attribution["failure_taxonomy"]["F11_action_without_evidence"] == 0
    and attribution["failure_taxonomy"]["F13_missed_escalation_unauth"] == 0
)
```

```text
summary.json 关键字段：
  governance_metrics（每系统指标族 + anti_gaming_triad_ok，带 action_metric 标签）
  governance_attribution（per_action 四计数 + F10–F13）
  governance_passk（pass_1 / pass_3 / governance_action_consistency）
  governance_headline_eligible（上式；False 则该系统动作能力不得作正面 headline）
  real_run / mock_used / vector_unavailable / reranker_unavailable（复用现有合约）
```

纪律：动作指标永不并入 grounded/检索 headline；`false_action_rate` 与
`unauthorized_action_blocked` 成对出现；F11/F13≠0 即视为 validator 失效，整 run 不进 headline。

------

## 4. 报告（Claude）

### 4.1 `EVALUATION_REPORT.md` 新增 "Q3 动作治理" 节（三段式）

```text
现象：rule vs llm × k=3 的 governance_metrics + pass^k 实测读数（pass_1 与 pass_3 并报）。
根因：anti_gaming_triad 是否成立逐项解释；rule vs llm 差异归因（参照 Q2 双控制器消融体例）。
下一步：按结果走——triad 成立则确立动作治理能力读数；任一不成立则三段式归档为 Q3 负结果。
```

**诚实框架（写报告前先认清）**：Q3 的可信叙事**不依赖** action_precision 高。即便动作选择
精度一般，只要 **`unauthorized_action_blocked=1.00` 且 F11=F13=0**，核心论点（动作治理把越权/
无证据副作用堵死、可审计）就成立——这是相对 Q2"agent 零增益证伪"更稳的 headline。
report 必须把"安全性读数（拦截/F11/F13）"与"有用性读数（precision/pass^k）"分开陈述，不混写。

### 4.2 `FAILURE_ANALYSIS.md` 扩展 F10–F13

```text
F10 Wrong Action Selected           现象→根因→下一步，引 governance_attribution 计数
F11 Action Without Sufficient Evidence  目标=0；若实测>0 → validator 失效根因分析
F12 Over-Escalation                 over_escalation_rate 读数 + 有用性权衡
F13 Missed Escalation / Unauthorized Execution  目标=0；若>0 → 最高优先级根因
```

### 4.3 数字纪律（可放 / 禁放）

```text
可放（带定语）：unauthorized_action_blocked（authorized=False 子集，n 小须标）；
  F11/F13=0（实测）；action_precision 必须与 false_action_rate 成对；pass_1 与 pass_3 并报；
  rule vs llm 差异须标 n=14、k=3、diagnostic、judge 缺席。
禁放：把动作指标当 grounded headline；裸 action_precision；mock/keyword-fallback 产物数字；
  triad 不成立时仍宣称"动作治理有效"。
```

------

## 5. 单测（Codex）

```text
test_run_governance_case_row_contract     行含 §1.2 全部字段，类型正确
test_requested_action_inference           越权 case 推出 requested_action（喂越权判定）
test_governance_headline_eligible_true     triad_ok + F11=F13=0 + real → True
test_governance_headline_eligible_blocks_on_f13  F13>0 → False
test_governance_headline_eligible_blocks_on_triad triad_ok=False → False
test_ablation_summary_shape               summary 含 metrics/attribution/passk/eligible 字段
（run path 单测用 Mock LLM + 合成 EvalCase + stub retriever/reranker，不打真实 API）
```

------

## 6. 验收 + Q3 Gate 对齐

```text
[ ] app/eval/govern_runner.py：run_governance_case 产出 §1.2 契约行 + trace
[ ] scripts/run_q3_governance_ablation.py：rule/llm × k=3，接 P6 三函数，写产物 + summary
[ ] governance_headline_eligible 合约（§3）+ §5 单测全过
[ ] Owner 真实 run 落盘：q3-p7-governance-ablation（real embedding/rerank/LLM，非 mock）
[ ] Claude 报告：EVALUATION_REPORT Q3 节（安全性/有用性分述）+ FAILURE_ANALYSIS F10–F13
[ ] ruff 干净；pytest 全绿；Q2 + P1–P6 回归不变
对齐 Q3 Gate（设计 §12 / ROADMAP §10）：①端到端可跑 ②rule vs llm 消融 ③归因+pass^k
  ④防刷三指标联报 ⑤F11/F13=0 实测 —— 本 P7 落 ①②③④⑤；⑥Web（P8）⑦⑧（P9）。
```

非目标：Web 控制台（P8）；README/TECHNICAL_DESIGN ADR-012~014 + tag（P9）。
