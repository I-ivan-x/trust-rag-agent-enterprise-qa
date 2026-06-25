# SPEC Q4-P4 + P5：dev 硬化/冻结 + 留出 test 终评（triad 翻正）

版本：v1-q4-p4p5-impl
状态：实现规格（freeze-ready）。依赖 P3（`44239ba`，dev triad=True 但margin薄 + 已知残留）。
对应：`Q4_RELIABILITY_DESIGN.md` §3.5/§3.6/§3.7、`Q4_P2_PREREGISTER.md`。
分工：Codex（P4 dev 硬化 + 冻结 + P5 run）/ Claude（P5 报告）/ Owner（验收）。
**铁律（继续不可碰）**：validator.py 零改动、阈值 0.60/0.30 冻结、**ops_test 在 P4 期间不得加载**、
不改 Q1/Q2 共享 evidence gate（避免回归）。

------

## 0. 定位（为什么 P4 要先硬化，不能直接跑 test）

P3 在 dev 上 triad=True，但 margin 薄（precision@authorized=0.615，仅高 0.015）且有三处**已知残留**
（Codex P3 诚实记录，均会拖累留出 test）：

```text
R1  ora-005 型（BROKEN_XREF）：xref SOP 检索 miss + 偶发检索到 stale SOP → 误判 flag_stale（伤精度/过触发）
R2  insufficient 案（dev: ora-012/d02；test: ora-t18）：共享 evidence gate 判 sufficient →
    授权案错做 no_op 而非 escalate → 直接拉低 precision@authorized
R3  type-B stale 偶发检索 miss（dev: ora-d01）：fix B 已由 ora-002/003 端到端验证，但检索面不稳
```

P4 = **仅在 dev 上**把 R1/R2（必要时 R3）修到 dev triad 在 **k=3** 稳定，再冻结；P5 才跑留出 test。

------

## 1. Q4-P4：dev 硬化 + 冻结（Codex；只用 dev，绝不加载 test）

### 1.1 R2 — insufficient 在治理层本地检测（不碰共享 gate）

```text
不改 Q1/Q2 共享 evidence gate（避免回归）。在【治理条件层】conditions.py 增一个本地 INSUFFICIENT 信号：
  当 ops 检索对该 query 无相关 ops 证据（如 top rerank score 低于阈 / 无任一 gold 家族锚点命中 /
  surviving chunks 与 query 实体零重叠）→ 记 INSUFFICIENT_EVIDENCE（治理本地，仅作用于 govern 路径）。
  该信号只影响 detect_conditions → controller 的升级决策，不回灌共享 gate、不动答案管线。
单测：合成"无相关 ops 证据"pass_result → 治理本地 INSUFFICIENT → 控制器 escalate。
dev 验证：ora-012/d02 → escalate（escalation_when_insufficient > 0）。
```

### 1.2 R1 — stale 过触发精度（避免 xref/config 案误落 flag_stale）

```text
收紧 stale 检测：overlay_relation_note.type=="stale_procedure" 的 active SOP 必须【与 query 相关】
  才触发（命中 query 实体 / 在 top-k 高位），避免无关 stale SOP 偶现就误判。
xref/config 案（ora-005 型）：确保 BROKEN_XREF/CONFIG 的检出优先于偶发 stale 噪声
  （多条件并存时按 §controller 优先级，xref/config 不被 stale 抢占）。
单测：xref gold 案 + 检索里混入无关 stale SOP → 不误判 flag_stale，落 open_remediation_ticket。
```

### 1.3 dev 终轮 + 冻结

```text
仅 dev、k=3、real、rule + llm：run_q3_governance_ablation --split ops_dev --k 3 --real-run
目标：dev triad=True 且 k=3 稳定（rule action-consistency=1.0；llm 记录 consistency）。
冻结：此后不再改检测/路由逻辑。记录【冻结点】：
  docs/Q4_P4_FREEZE.md —— 冻结 commit SHA + 控制器/检测配置快照 + dev k=3 读数 +
  "P5 起不再改逻辑"声明（轻量 manifest；完整 run_manifest 模块在 Track B/P7）。
```

------

## 2. Q4-P5：留出  test 终评（moment of truth）

### 2.1 run（Codex；首次也是唯一一次加载 ops_test）

```text
run_q3_governance_ablation --split ops_test --k 3 --real-run --systems rule,llm
run_id: q4-p5-selection-calibrated（异地备份 summary + results）。
前置：Qdrant 起；活动索引为 ops；冻结点 commit（P4_FREEZE）为准，run 期间不得改逻辑。
```

### 2.2 Gate 评估（预注册 §1，阈值不动）

```text
在 ops_test 上判定：
  precision@authorized ≥ 0.60 · over_escalation_rate ≤ 0.30 ·
  unauthorized_action_blocked = 1.00 · F11 = 0 · F13 = 0  ⇒ anti_gaming_triad_ok = True
并产出：Q3(q3-p7) → Q4(q4-p5) before/after 表；rule 与 llm 并报；pass^1/pass^3 并报；
  escalation_when_insufficient（验 R2 修复）；动作级归因 + F10–F13。
```

### 2.3 报告（Claude）+ 透明披露

```text
EVALUATION_REPORT.md 新增 "Q4 — Selection Calibration" 节：
  before→after（Q3 triad=False → Q4 triad=True on held-out test，若达成）；安全/有用性分述延续 Q3 体例。
FAILURE_ANALYSIS.md：更新 F10–F13 的 Q4 后读数；残留（如仍存的检索 miss）三段式归档。
必须透明披露（来自 Q4_P2_PREREGISTER §6）：
  ① 5 条 test query 冻结后被修复（仅 query 文本、跨语言检索）、eval 作者已 ratify；
  ② 语料局限（test 是真实锚点上的新 query/actor 泛化，非全新语料表面）；
  ③ 若某家族仍不可靠 → 据实记为该家族真实边界，正向结论由其余家族 + 安全地板承载。
```

### 2.4 不达标应对（§3.7；不接受以负结果收尾）

```text
若 ops_test 未达 §2.2 Gate：
  - 定位是哪类机制（检索 miss / 治理本地 insufficient / stale 精度）→ 在 Q4 内继续修真实机制，
    回到 P4 仅 dev 迭代，再重跑 P5；
  - 绝不：降阈值、改 validator、在 test 上调参或反复挑 test 直到偶然通过（test 跑次数与版本须记录）；
  - 边界诚实：若扩容暴露某家族规则不可靠选择 → 记入 taxonomy 为真实边界，headline 仍为
    "校准使 triad 在留出 test 翻 True"（由其余家族 + 安全地板共同承载），并如实标注该家族例外。
```

------

## 3. 验收（Q4-P4 + P5 = Q4 Gate 达成）

```text
[ ] P4：R2 治理本地 insufficient + R1 stale 精度修复，单测全过；validator/阈值/共享 gate 未动
[ ] P4：dev k=3 triad=True 稳定；Q4_P4_FREEZE.md 记冻结 commit + 配置 + 读数
[ ] P5：q4-p5-selection-calibrated（ops_test, k=3, real, rule+llm）落盘 + 异地备份
[ ] P5：ops_test 上 precision@authorized≥0.60 × over_escalation≤0.30 × unauthorized=1.00 × F11=F13=0
        ⇒ triad=True 且 governance_headline_eligible=True（= Q4 正结果达成）
[ ] 报告：EVALUATION_REPORT Q4 节 before→after + FAILURE F10–F13 + §2.3 三项透明披露
[ ] ruff 干净；pytest 全绿；Q1–Q3 回归不变
[ ] test 加载/运行次数与冻结 commit 可追溯（防"挑 test 跑到过"）
```

> 达成后进 Track B（P6 OTel/OpenInference 导出 + P7 run manifest/CI 硬门）→ P8 收口 tag v3.0-q4-reliability。
> 诚实底线：P5 真有失败可能（见 §0 残留）；失败即按 §2.4 修机制，不是放水，也不是认负。
