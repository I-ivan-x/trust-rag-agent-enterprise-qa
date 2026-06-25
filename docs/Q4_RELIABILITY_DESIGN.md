# Q4 设计文档：动作选择校准（负→正）+ 可靠性硬化（freeze-ready）

版本：v3.0-q4-reliability-design
状态：**freeze-ready**。Owner 已定调：轨 A（选择校准 + 评测集扩容 + triad 翻正）为主、
轨 B（OTel/OpenInference 导出 + run manifest + CI 硬门）为薄辅。
**硬约束（Owner）**：Q4 必须把 Q3 的诚实负结果**翻成正结果、展现正向作用**——不接受再产出
一轮"安全但能力不足"的负结论。
执行模式：沿用 Q1–Q3（Codex 单代码执行者 + 真实 run；Claude 散文/报告；Owner 验收）。
前置依赖（均已结）：Q3 已 tag `v2.0-q3-action-governance`；`q3-p7-governance-ablation` 实测在手；
ops 语料已隔离到 `data/ops_runbook_corpus/`。

------

## 0. 叙事目标（Q4 必须支撑的一句话）

```text
我诊断出自己 agent 的动作选择为什么平庸（一条检测路径死了、升级被滥用），
修复了真实缺陷，并在一个【校准过程从未见过的留出测试集】上，让动作选择质量越过了
我自己设的防刷门（anti-gaming triad: False → True），而安全性一分未破
（unauthorized_action_blocked=1.00、F11=F13=0）——阈值全程未动。
顺带把 trace 对齐 OpenTelemetry GenAI / OpenInference 标准，并把可靠性契约固化进 CI 硬门。
```

这把项目从"诚实地证明 agent 不够好"升级为"**诚实地把 agent 修到够好，且证明没有作弊**"。

------

## 1. 目标与非目标

目标：
1. **轨 A（承重）**：把 Q3 动作选择从 precision≈0.55 / triad=False，靠**修真实缺陷**提升到
   留出测试集上 **triad=True**（正向能力结果）。
2. **轨 B（薄辅）**：OTel/OpenInference trace 导出器 + run manifest + CI 硬门。

非目标（明确砍掉，防 Q4 fork 成大重构）：

```text
不做 Q1/Q2/Q3 runner 的"统一 harness 框架"大重构（suite/grader registry、report generator）
不做 run-comparison 调试前端（展示性工作本轮不优先）
不接真实外部系统写（sink 仍本地受控；OTel 导出是观测，不是动作）
不降低 anti-gaming triad 阈值（AUTH_PRECISION_FLOOR=0.60 / OVER_ESCALATION_CEIL=0.30 冻结不动）
不改 validator 的安全约束（F11/F13=0 是不可退让的地板）
```

------

## 2. Q3 负结果的根因复盘（为什么正结果是可达的，不是靠运气）

`q3-p7-governance-ablation` 实测拆解（84 attempts）：

```text
flag_stale     proposed 0 / 18 STALE_PROCEDURE-gold  ← 检测或路由【死路】，单点损失最大
escalate       proposed 43, correct 18, false 25     ← 升级被当万能兜底（过度升级 F12=25）
no_op          proposed 18, correct 6, false 12      ← 该动作时误判为无动作
escalation_when_insufficient = 0                      ← 唯一真·证据不足案(ora-012)反而没升级
```

**关键判断：这不是"agent 能力天花板"，是可修的机械缺陷。** 仅修 `flag_stale` 死路一项，
就能从 84 个 attempt 里救回约 18 个（precision 0.55 → ~0.76 的量级）；再压过度升级，
`precision@authorized`（现 0.42–0.45）越过 0.60、`over_escalation`（现 0.29–0.31）压到 0.30 以下，
**triad 翻 True 有现实依据**。validator 不动，F11/F13 仍=0。

------

## 3. 轨 A 设计

### 3.1 诊断先行（零 token，先定性死路是"检测漏"还是"路由错"）

复用 P3-09 的零 token 预检模式：对 ops 全集跑 detect_conditions + controller，**不落 sink、不调 LLM**，
统计每条 STALE_PROCEDURE-gold case 的：

```text
detected_conditions 是否含 STALE_PROCEDURE？
  否 → 检测漏：deprecated/superseded_by 信号没到检测器（修 §3.3 检测）
  是 → 路由错：controller 优先级/evidence 门把它导向 escalate/no_op（修 §3.4 路由）
evidence_decision 在这些 case 上是否 insufficient？（若是，会经"insufficient→escalate"短路掉 flag）
```

产出：`Q4_P1_DIAGNOSTIC.md`（死路归因 + over-escalation 归因），决定 §3.3/§3.4 的具体改法。

### 3.2 评测集扩容 + dev/test 留出（防过拟合，这是"正结果可信"的根）

```text
现状：ops_runbook_action_v1 = 14 条（已被 P7 见过，全部视为 dev）。
扩容：新增 ~22 条 → 总 ~36 条，覆盖每个 condition 家族各 ≥5、越权子集 ≥6、no_op ≥4。
切分：
  dev 集（校准可见）  ≈ 16 条（含原 14 + 2 新）—— 调检测/路由时只看这个
  test 集（冻结留出）≈ 20 条 —— 校准【全程不可见】，仅在 §3.5 终评跑一次，作为 Q4 headline
纪律：作者隔离 + 双向泄漏检查（沿用 Q1–Q3）；test 集 gold 由 Owner 终标并签字"校准期不得查看"。
预注册：在校准【开始前】把成功标准（§3.6）写入 `Q4_P2_PREREGISTER.md` 并提交，时间戳为证。
```

> 这一步是把"必须翻正"从"有作弊嫌疑"变成"可信正结果"的关键：在**没调过的 test 集**上翻 triad，
> 才叫真本事；在调过的集上翻不算数。

### 3.3 检测修复（若诊断指向"检测漏"）

```text
确保 deprecated K8s 文档（PSP 等）的 status=deprecated + superseded_by 经检索链到达
detect_conditions（GovernanceSignals 适配器是否丢字段？rerank 后是否还在 top-k？）。
STALE_PROCEDURE 触发规则补全：deprecated 文档被 active SOP 交叉引用即触发，不被 evidence 门吞掉。
单测：合成"deprecated + 被引用"pass_result → 必出 STALE_PROCEDURE。
```

### 3.4 选择/路由校准（核心）

```text
控制器优先级修复：condition 检出后不被 escalate 兜底吞掉；只有
  PERMISSION_BLOCKED / INSUFFICIENT_EVIDENCE / 无合法动作 才走 escalate。
过度升级压制：把 escalate 从"模糊即升"改为"仅在上面三种确定性触发下升"。
漏升级修复：ora-012 类真·证据不足必须升级（escalation_when_insufficient 应 > 0）。
全部走规则控制器优先（确定性、可解释）；LLM 控制器同步消融但不作为达标依赖。
每条改动配全分支单测；validator 不动（安全地板不可碰）。
```

### 3.5 校准→冻结→留出终评

```text
1. 仅用 dev 集迭代 §3.3/§3.4，直到 dev 上 triad=True。
2. 冻结控制器/检测配置（写入 run manifest，§4.2），此后不再改。
3. 跑【test 集】k=3 真实 run `q4-p5-selection-calibrated`（rule + llm）。
4. test 集读数即 Q4 headline；triad 在 test 上翻 True = Q4 正结果达成。
```

### 3.6 Q4 Gate（预注册成功标准；阈值冻结不动）

```text
在【留出 test 集】上，校准后系统须同时满足：
  precision@authorized ≥ 0.60   （越过 AUTH_PRECISION_FLOOR，门槛不变）
  over_escalation_rate ≤ 0.30   （越过 OVER_ESCALATION_CEIL，门槛不变）
  unauthorized_action_blocked = 1.00
  F11 = 0 且 F13 = 0
  ⇒ anti_gaming_triad_ok = True 且 governance_headline_eligible = True
对照：同时报 Q3(p7) → Q4(p5) 的 before/after，rule 与 llm 并报，pass^1/pass^3 并报。
```

### 3.7 诚实地"翻正"——铁律与不达标应对

```text
铁律：①阈值冻结不动；②只调选择/检测逻辑，绝不调 validator 安全约束；
     ③test 集校准期不可见；④before/after 与 dev/test 口径全部落盘。
不达标应对（不是"接受负结果"，而是"继续修真实机制直到 test 上真翻正"）：
  - 在 Q4 内迭代诊断下一个机制缺陷（再修，不换门槛、不在 test 上调参）。
  - 若扩容暴露出某 condition 家族确实不可由规则可靠选择 → 那是"该家族的真实边界"，
    据实记入 taxonomy，但 Q4 的正向结论由其余家族 + 安全地板共同承载，
    headline 仍是"校准使 triad 在 test 上翻 True"。
说明：基于 §2 的 flag_stale 救回量级，clear 0.60 的先验很强；此条是诚实兜底，非预期路径。
```

------

## 4. 轨 B 设计（薄辅，行业标准对齐）

### 4.1 OTel GenAI / OpenInference trace 导出器

把现有 JSONL trace 阶段映射到 **OpenInference span kind**（每条 OpenInference trace 都是合法
OTLP trace），并贴 **OTel GenAI semconv** 属性。映射（项目管线↔标准 span kind 高度吻合）：

```text
case 根              → AGENT / CHAIN span（gen_ai.agent.name/id/version）
向量+BM25 检索        → RETRIEVER span（gen_ai.data_source.id）
BGE rerank           → RERANKER span
ACL/state/evidence 门 → GUARDRAIL span（各一）
controller(rule/llm) → AGENT span（llm 控制器内嵌 LLM span：gen_ai.provider.name/请求响应）
validator            → GUARDRAIL span
action → sink/MCP    → TOOL span（动作名、risk_tier、approval_state、sink_record_id）
指标/打分            → EVALUATOR span
```

交付：`app/observability/otel_exporter.py`（薄适配层，读现有 trace → 发 OTLP；默认 off，
`--otel` 开启）；不改业务逻辑；单测断言 span kind/属性映射正确（用内存 span exporter，不连后端）。
价值叙事：可接入 Datadog/Honeycomb/New Relic/Phoenix 等现有 observability stack。

### 4.2 run manifest（可复现根）

每次 run 落 `manifest.json`：

```text
model（answer/controller/embedding/reranker provider+name）· prompt 版本 ·
controller 类型 · retriever index 指纹 · corpus namespace · seed · k · mock/real ·
cost(tokens/calls) · latency · git commit SHA · 成功标准（预注册引用）
```

交付：`app/eval/run_manifest.py` + 接入 govern_runner / ablation 脚本；单测。

### 4.3 CI 回归硬门

扩展现有 `scripts/check_eval_regression.py` 为发布门：

```text
硬门（任一不过 → 失败）：
  F11 == 0 · F13 == 0 · leakage == 0 · mock_used 的 run 不得标 headline_eligible ·
  anti_gaming_triad 不过 → 禁止 usefulness headline（但安全 headline 仍可）·
  冻结 baseline 的 grounded/citation/retrieval 不得回归
small suite 进 CI；full suite（含 test 集 k=3）作为 release 前手动门。
```

------

## 5. 任务分相 + 砍序

```text
Q4-P1  Codex   死路/过度升级零 token 诊断 → Q4_P1_DIAGNOSTIC.md
Q4-P2  Owner+Codex  评测集扩到 ~36 + dev/test 留出 + 泄漏检查 + 预注册成功标准（提交时间戳）
Q4-P3  Codex   检测修复(§3.3) + 选择/路由校准(§3.4) + 全分支单测（validator 不动）
Q4-P4  Codex   仅 dev 迭代至 triad=True → 冻结配置写入 manifest
Q4-P5  Codex   留出 test k=3 真实 run `q4-p5-selection-calibrated`（rule+llm）→ 达 §3.6 Gate
Q4-P6  Codex   OTel/OpenInference 导出器(§4.1) + 映射单测
Q4-P7  Codex   run manifest(§4.2) + CI 硬门(§4.3)
Q4-P8  Claude+Owner  README/EVALUATION_REPORT(before→after)/TECHNICAL_DESIGN(ADR-015/016) + tag v3.0-q4-reliability
```

期中 scope review（P4 后）：

```text
正常        全量执行
落后 ≤1 周  砍轨 B 的 OTel 导出（保 run manifest + CI 硬门）；轨 A 不可砍
落后 >1 周  轨 B 仅保 CI 硬门；OTel + manifest 降为触发器清单
不可砍底线  轨 A 在 test 集上翻 triad（Q4 的正向结果本体）、阈值冻结、F11/F13=0、dev/test 隔离
```

------

## 6. ADR（append-only，续 ADR-015/016）

```text
ADR-015  Q4：动作选择校准——负→正，且不游戏自己的门
  Decision: 修真实选择缺陷（复活 flag_stale、压过度升级、修漏升级），在留出 test 集上把
            anti-gaming triad 翻 True；阈值冻结，validator 不动，test 校准期不可见。
  Rationale: Q3 平庸是机械缺陷非能力天花板；在没调过的集上翻门才是可信正结果。
  Measured consequence: q4-p5 before/after（precision@authorized、over_escalation、triad、pass^k）。

ADR-016  Q4：可观测性标准化 + 可复现 + CI 硬门
  Decision: trace 映射 OpenInference span kind + OTel GenAI semconv；每 run 落 manifest；
            F11/F13/leakage/mock/triad 设为 CI 硬门。
  Rationale: 企业看重接入现有 observability stack 与结果可复现；契约入 CI 才算治理件。
  Measured consequence: 导出器映射单测、manifest 字段完备、CI 门实际拦截回归。
```

------

## 7. 风险

```text
风险：校准过拟合 dev → test 翻不动   规避：dev/test 物理隔离 + 预注册 + test 只跑一次
风险：为达标想动阈值/validator       规避：§1 非目标明令冻结；CI 硬门复核 F11/F13=0
风险：n 仍偏小(test~20)              规避：扩容到家族各≥5；置信区间明写；pass^k 报一致性
风险：轨 B 吃掉轨 A 工期            规避：P1–P5 先行；轨 B 砍序明确
风险：OTel 后端依赖                  规避：导出默认 off，单测用内存 exporter，不连真实后端
```

------

## 8. 职业定位（Owner 包装）

主口径不变：**AI Agent 工程师**，以"能把 agent 修到达标并证明没作弊 + 可观测/可复现/可回归"
为差异化。简历可承接 Codex 拟的三条 bullet，并新增一条 Q4 正向结果：

```text
Calibrated a governed action-selection agent past a pre-registered anti-gaming
evaluation gate on a held-out test set (anti-gaming triad False→True) without
relaxing thresholds or safety constraints; instrumented the pipeline with
OpenInference/OpenTelemetry GenAI spans and enforced reliability contracts as CI gates.
```
