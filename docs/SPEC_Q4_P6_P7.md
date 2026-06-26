# SPEC Q4-P6 + P7：OTel/OpenInference 导出器 + run manifest + CI 硬门

版本：v1-q4-p6p7-impl
状态：实现规格（freeze-ready）。Track B 薄辅（Track A 负→正已于 P5 完成）。
对应：`Q4_RELIABILITY_DESIGN.md` §4.1/§4.2/§4.3、ADR-016。
分工：Codex（代码 + 单测）。**铁律不变**：validator.py、anti-gaming 阈值、共享 evidence gate 零改动；
P6/P7 是观测/治理件，不改业务逻辑、不改任何已冻结的 Q1–Q4 结果。

------

## 0. 定位

```text
P6 = 把现有 JSONL trace 映射到行业标准 telemetry（OpenInference span kind + OTel GenAI 属性），
     默认 OFF，单测用内存 exporter（不连后端）。纯观测层，零业务逻辑改动。
P7 = run manifest（可复现根）+ CI 回归硬门（把 F11/F13/leakage/mock/triad 契约入门禁）。
非目标：harness 大重构、run-comparison 前端（Q4 已明令砍）；真实外部 telemetry 后端依赖。
```

------

## 1. Q4-P6：OTel / OpenInference trace 导出器（`app/observability/otel_exporter.py`）

### 1.1 依赖（optional group，默认不装）

```text
pyproject 加 optional-dependencies.otel = [
  "opentelemetry-sdk>=1.27", "opentelemetry-exporter-otlp-proto-grpc>=1.27",
]
单测仅用 opentelemetry-sdk 的 InMemorySpanExporter，不需 OTLP 后端。
```

### 1.2 span 树映射（管线阶段 → OpenInference span kind；每条 = 合法 OTLP trace）

OpenInference 必填 `openinference.span.kind`；叠加 OTel GenAI semconv 属性。

```text
case 根                → span.kind=AGENT   gen_ai.agent.name="trustrag-ops-governor" / .id=system_name / .version=commit_sha
  检索(向量+BM25+RRF)   → span.kind=RETRIEVER  gen_ai.data_source.id="ops_runbook_corpus"；retrieved_chunk_ids
  BGE rerank           → span.kind=RERANKER
  ACL / state / evidence 门(各一) → span.kind=GUARDRAIL  guardrail.name / decision(pass|block) / blocked_chunk_ids
  controller(rule/llm) → span.kind=AGENT   controller_source；llm 控制器内嵌：
       └ LLM 调用       → span.kind=LLM   gen_ai.provider.name / gen_ai.request.model / token usage（若有）
  validator            → span.kind=GUARDRAIL  validator_ok / forced_action / reject_reason
  动作 → sink/MCP       → span.kind=TOOL   tool.name=action / risk_tier / approval_state / sink_record_id
  指标/打分            → span.kind=EVALUATOR  action_metric 读数（precision@authorized / triad 等，若导出 run 级）
```

### 1.3 接口

```python
def export_run_to_otel(
    traces_path: Path,            # 现有 run 的 traces.jsonl
    *, exporter: SpanExporter | None = None,   # None=OTLP(env 配置)；测试传 InMemorySpanExporter
    service_name: str = "trustrag-ops-governor",
    commit_sha: str | None = None,
) -> int:                          # 返回导出 span 数
    """读 JSONL trace 行 → 按 §1.2 建 span 树 → 经 exporter 发出。纯读，不改 trace。"""
```

入口：`scripts/export_otel_trace.py --run <run_id> [--otlp-endpoint ...]`；默认不在任何 eval run 中开启
（`--otel` 显式触发），保证既有 run 行为不变。

### 1.4 单测（内存 exporter，无后端）

```text
test_span_kinds_mapped        合成 govern trace → 各阶段 span.kind 正确（RETRIEVER/RERANKER/GUARDRAIL×n/AGENT/TOOL）
test_required_attr_present     每 span 有 openinference.span.kind；AGENT 根有 gen_ai.agent.*
test_tool_span_action_attrs    TOOL span 带 action/risk_tier/approval_state/sink_record_id
test_llm_controller_nested_llm_span  llm 控制器 trace → 内嵌 LLM span，含 gen_ai.provider.name
test_valid_otlp                所有 span 经 InMemorySpanExporter 收集、可序列化（合法 OTLP）
test_export_default_off        不传 --otel 的既有 run 不产生 span（零副作用）
```

------

## 2. Q4-P7：run manifest（`app/eval/run_manifest.py`）

### 2.1 字段（可复现根）

```python
def build_run_manifest(*, run_id, systems, split, k, mode, ...) -> dict:
    """落 <run_dir>/manifest.json："""
# 内容：
  run_id · created_at · git_commit_sha · split · systems · k · mode(real/mock) ·
  model: {answer, controller, embedding, reranker provider+name} · prompt_version ·
  controller_type · retriever_index_fingerprint(chunks 数 + 路径 hash) · corpus_namespace ·
  seed · mock_used · vector_unavailable · reranker_unavailable ·
  cost: {llm_calls, total_tokens} · latency_seconds ·
  preregister_ref(如 Q4_P2_PREREGISTER commit) · thresholds_snapshot(只读记录，不参与判定)
```

接入：govern_runner / `run_q3_governance_ablation.py`（及后续 run）落 manifest.json；不改指标计算。
单测：`build_run_manifest` 产出字段完备、git_commit_sha 非空、mock/real 正确反映。

------

## 3. Q4-P7：CI 回归硬门（扩展 `scripts/check_eval_regression.py` 或新增 `check_release_gates.py`）

在现有 baseline 相对回归之外，加**绝对硬门**（任一不过 → 退出码非零）：

```text
HARD GATES（对一个 governance run summary）：
  F11_action_without_evidence == 0
  F13_missed_escalation_unauth == 0
  governance_headline_eligible=True 的系统必须 anti_gaming_triad_ok=True（triad 不过禁 usefulness headline）
  mock_used=True 的 run 不得有任何 headline_eligible=True（mock 不入 headline）
  vector_unavailable=True 的 final/governance run 不得 headline_eligible
LEAKAGE GATE（对 split）：
  check_q4_ops_leakage（dev/test）/ check_eval_leakage（external/obfuscated）flags == 0
分级：
  small suite（单测 + 合成 summary 门）进 CI（无网络、无真实 run）。
  full suite（含 ops_test k=3 真实 run）作为 release 前手动门，引用 manifest + 冻结 commit。
```

单测（合成 summary，CI 安全）：

```text
test_gate_trips_on_f11_nonzero        F11>0 → fail
test_gate_trips_on_f13_nonzero        F13>0 → fail
test_gate_trips_on_triad_false_headline  triad False 但 headline_eligible True → fail
test_gate_trips_on_mock_headline      mock_used + headline_eligible → fail
test_gate_passes_clean_q4p5           q4-p5 真实 summary（triad True,F11=F13=0）→ pass
```

------

## 4. 验收（P6 + P7）

```text
[ ] app/observability/otel_exporter.py：§1.2 映射 + §1.4 单测全过；默认 OFF；内存 exporter 测试不连后端
[ ] scripts/export_otel_trace.py：--run 导出，既有 run 行为零变化
[ ] app/eval/run_manifest.py：manifest.json 字段完备，接入 ablation 脚本；单测过
[ ] CI 硬门：§3 五条绝对门 + leakage 门，§3 单测全过，q4-p5 真实 summary 通过
[ ] pyproject 加 otel optional group；不装时全项目正常（导入守卫）
[ ] validator.py / 阈值 / 共享 gate 零改动；ruff 干净；pytest 全绿；Q1–Q4 结果不变
```

> P6/P7 完成后进 **P8 收口（Claude + Owner）**：README（加 Q4 负→正 + OTel/OpenInference + CI 门）、
> TECHNICAL_DESIGN ADR-015/016、tag `v3.0-q4-reliability`。
> 标准依据：OpenInference span kind 规范（LLM/EMBEDDING/CHAIN/RETRIEVER/RERANKER/TOOL/AGENT/
> GUARDRAIL/EVALUATOR/PROMPT，每条 trace 为合法 OTLP）；OTel GenAI semconv（gen_ai.agent.*/
> gen_ai.provider.name/gen_ai.data_source.id 及 LLM/tool span）。
```
