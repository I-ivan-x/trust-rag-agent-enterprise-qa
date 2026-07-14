# TrustRAG — Project Overview (job-search brief)

> **One-line pitch.** An enterprise RAG-Agent built reliability-first: I measured
> what it does (zero false answers, zero unauthorized actions), proved where it was
> weak instead of hiding it, then *fixed a diagnosed weakness and showed the fix clear
> my own anti-gaming evaluation gate on a held-out set — thresholds frozen.*

**Positioning:** AI Agent / LLM-application engineer, differentiated by *agent
reliability & evaluation* — I don't just wire up RAG and tool-calls, I make an agent
**measurable, auditable, regression-gated, and honest about its own limits.**

Built solo across four tagged quarters (Q1–Q4) plus the active Q5 Agent Infra phase,
with a 553-test suite (552 passing, one opt-in real smoke skipped at the Q5 v3 real-dev
diagnostic checkpoint). LLM work uses external models for evaluated runs; retrieval is real
(`bge-small-en-v1.5` + `bge-reranker-base` + Qdrant + BM25/RRF).

---

## The arc (each quarter a coherent, tagged result)

| Quarter | Theme | Headline result (measured, real runs) |
| --- | --- | --- |
| **Q1** `v0.3-q1-hard-demo` | Trustworthy RAG + anti-self-deception eval | **0.00** false-answer rate, **1.00** citation structural validity; contamination control (raw 0.20 → grounded **0.00**); honestly reported the cost: grounded 0.24 at false-refusal 0.46 |
| **Q2** `v1.0-q2-agentic-eval` | Typed-action recovery agent + eval governance | Built typed action space + rule-vs-LLM ablation + pass^k; **falsified** an agent gain honestly (gated 0.2273 vs agentic 0.2727, rule==LLM); shipped governance without a judge after proving none was deployable |
| **Q3** `v2.0-q3-action-governance` | Trust layer promoted from answers to **actions** | Evidence-aware ops copilot: **unauthorized-action blocked 1.00**, F11/F13 **0** (zero unauthorized / no-evidence side effects); honestly reported selection was mediocre (anti-gaming triad **False**) |
| **Q4** `v3.0-q4-reliability` | Turn the negative positive + standardize observability | On a **held-out** test set, fixed real defects → anti-gaming triad **False→True** (precision@authorized 0.4545→**0.6471**), thresholds frozen, safety unbroken; added OpenInference/OTel traces + run manifest + CI hard gates |

The throughline: **a governance system that audits itself.** Every negative result has a
traced root cause (failure taxonomy F1–F13) and a planned/landed fix; every headline
number is guarded by a code contract, not discipline.

---

## What makes it more than "a RAG project"

1. **Grounded-only headline.** The reported accuracy metric (`grounded_correctness`)
   scores only if the answer is correct *and* every citation comes from retrieved
   context *and* a citation supports the core claim — parametric memory can't cheat it.
2. **Reporting eligibility is code, not a promise.** Runs carry `headline_eligible` /
   `mock_used` / `vector_unavailable` flags; mock or degraded runs are mechanically
   excluded from headline reporting (unit-tested).
3. **Governance promoted from answers to actions (Q3).** A typed, whitelisted
   side-effecting action space (`flag_stale` / `open_remediation_ticket` / `send_alert`
   / `escalate_to_human`) under a validator that re-runs ACL + evidence preconditions
   and a risk-tiered autonomy model (auto / human-approval / escalate). Proven on real
   runs: **zero unauthorized or no-evidence side effects.**
4. **An anti-gaming evaluation contract (Q3→Q4).** Usefulness can only be headlined if
   three metrics hold together (`unauthorized_blocked=1.0` × `precision@authorized≥0.60`
   × `over_escalation≤0.30`) — so an "escalate-everything" or mock controller can't fake
   a win. In Q4 I made the agent legitimately *clear* that gate.
5. **The negative-to-positive move, done honestly (Q4).** The Q3 weakness was a
   mechanical defect (a dead detection path), not a ceiling. I diagnosed it, fixed the
   mechanism, and proved the anti-gaming triad flips False→True on a **held-out** set
   the calibration never tuned on — thresholds frozen, validator byte-identical, both
   test runs archived, every deviation disclosed.
6. **Standardized reliability (Q4).** Traces export to OpenInference span kinds over
   OTLP + OpenTelemetry GenAI attributes (opt-in); each run emits a reproducibility
   manifest; reliability contracts (F11=0, F13=0, leakage=0, mock≠headline,
   triad-gates-usefulness) run as CI hard gates.

---

## Résumé bullets (drop-in)

- Built a trustworthy enterprise **RAG-Agent** (FastAPI, Qdrant, BM25/RRF, BGE rerank,
  fail-closed ACL/state/evidence gates) with **0.00 false-answer rate** and **1.00
  citation structural validity** on real external runs.
- Designed a reproducible **agent evaluation harness** — grounded-only metrics, leakage
  checks, pass^k reliability, action-level attribution, and **headline-eligibility code
  gates** that bar mock/degraded runs from being reported as wins.
- Extended answer-level trust gates to **side-effecting agent actions** with risk-tiered
  governance, human-approval routing, and audit traces — **zero unauthorized and zero
  no-evidence executions** in real ablation runs.
- Authored an **anti-gaming evaluation contract** (a 3-metric triad) that prevents
  all-refusal baselines, over-escalating controllers, and mock runs from claiming a
  headline; then **calibrated the agent past that gate on a held-out test set
  (triad False→True, precision@authorized 0.45→0.65) without relaxing any threshold.**
- Instrumented the pipeline with **OpenInference/OpenTelemetry GenAI** spans and enforced
  reliability contracts (F11=0, F13=0, leakage=0) as **CI hard gates**.

---

## 面试讲法（中文要点）

- **一句话故事**：别的作品集只摆正结果；我这个项目能**证明系统哪里不行、并用代码阻止自己乱报好成绩**，
  然后把一个诚实的负结果**靠修真实缺陷翻成正结果、且在没调过的留出集上验证、阈值一分没松**。这最像真实工程。
- **被追问"0.24 grounded 是不是太低"**：那是 fail-closed 的代价——瓶颈是"不答"不是"答错"（false-refusal 0.46，
  false-answer 0.00）。我把它当校准数据，不当遮羞布。
- **被追问"agent 有没有用"**：Q2 我**诚实证伪**了检索恢复 agent 的增益（rule==llm，一个 case 差）；Q3 把 agent
  做成有副作用的动作治理，安全性无懈可击但选择质量中等；Q4 才把选择质量修到越过我自己设的防刷门。
- **被追问"怎么保证没作弊翻门"**：dev/test 物理隔离 + 成功标准带时间戳预注册 + 阈值冻结 + validator 字节级未变 +
  两次 test run 全备份 + R1 修正在 dev 上 precision 不变/over-escalation 反降（真机制修复的判据）+ 所有偏离写进报告。
- **诚实定语**（不藏）：Q4 结果"真但薄"（过 ~1 个 case），6/17 残留是 ~30 篇小语料的检索不稳，已如实记为检索边界；
  下一步强化是扩独立语料表面，不是调参。

---

## Pointers

- Honest results & trade-offs: `README.md`, `docs/EVALUATION_REPORT.md`
- Latest outcome + web demo handoff: `docs/LATEST_RESULTS_AND_DEMO.md`
- Engineering discipline + execution evidence: `docs/ENGINEERING_DISCIPLINE.md`
- Active Q5 design + implementation handoff: `docs/Q5_ADAPTIVE_AGENT_DESIGN.md`,
  `docs/Q5_P5_PREREG_AMENDMENT_V2.md`, `docs/Q5_P5_PREREG_AMENDMENT_V3.md`,
  `docs/Q5_P5_DEV_V3_AUTHORING_REPORT.md`, `docs/Q5_P5_DEV_V2_READINESS.md`,
  `docs/Q5_P5_REAL_DEV_V3_NEGATIVE_DIAGNOSTIC.md`,
  `docs/SPEC_Q5_P5_H_POLICY_SEMANTIC_BINDING.md`, `docs/Q5_VALUE_FRONTIER_STRATEGY.md`,
  `docs/SPEC_Q5_P5_I_VALUE_FRONTIER_HARDENING.md`, `docs/Q5_IMPLEMENTATION_HANDOFF.md`
- Failure taxonomy F1–F13 with trace evidence: `docs/FAILURE_ANALYSIS.md`
- Design decisions (ADR-001…016) with measured consequences: `docs/TECHNICAL_DESIGN.md`
- Q4 negative→positive design + pre-registration: `docs/Q4_RELIABILITY_DESIGN.md`, `docs/Q4_P2_PREREGISTER.md`
- Runtime demo: `uvicorn app.main:app` → `/console/` (read→detect→act→govern console), `/docs` (Swagger)
- Recruiter-facing web demo: `cd frontend && npm run dev` → Astro/Tailwind snapshot showcase
- Tags: `v0.3-q1-hard-demo` · `v1.0-q2-agentic-eval` · `v2.0-q3-action-governance` · `v3.0-q4-reliability`
