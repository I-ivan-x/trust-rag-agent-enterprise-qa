# SPEC Q4-P8：收口 + tag v3.0-q4-reliability

版本：v1-q4-p8-closeout
状态：实现规格（freeze-ready）。**散文已由 Claude 预写**（ADR-015/016、README Q4 结果行 + 文档表）——
P8 对 Codex 而言是**机械收口 + tag**，只剩一处文档行需在 P6/P7 绿后粘贴（§2）。
分工：Codex（P6/P7 代码 + 本 P8 机械收口 + tag）。Owner（验收/确认 tag）。

------

## 0. 前置（已由 Claude 完成，勿重做）

```text
✅ EVALUATION_REPORT.md "Q4 — Selection Calibration" 节（before→after + §2.4 + 残留 + 三披露）
✅ FAILURE_ANALYSIS.md F10–F13 Q4 update
✅ TECHNICAL_DESIGN.md ADR-015（Q4 负→正，实测）+ ADR-016（观测/复现/CI，acceptance 契约）
✅ README.md "What works" Q4 行 + Q3 fails 行标注 resolved + 文档表 Q4 条目
```

------

## 1. P8 收口步骤（Codex，在 P6/P7 全绿之后）

```text
1. 确认 P6/P7 验收全过（SPEC_Q4_P6_P7 §4）：otel 导出器映射单测、run manifest 字段、CI 硬门单测，
   且 q4-p5 真实 summary 通过 CI 硬门；ruff 干净、pytest 全绿、Q1–Q4 结果不变。
2. 应用 §2 的 README 观测/CI 行（这是唯一需新增的散文，已写好待粘贴——P6/P7 存在后它才为真）。
3. ROADMAP §11：把 Q4-P6/P7/P8 标 ✅（附 commit）。
4. tag（§3）。
```

------

## 2. README 观测/CI 行（P6/P7 绿后由 Codex 粘贴；此前不得加，否则claim未built功能）

在 README "Why You Can Trust These Numbers" 列表末尾追加一条：

```markdown
5. **Standardized, gated reliability.** Pipeline traces export to OpenInference span
   kinds over OTLP with OpenTelemetry GenAI attributes (opt-in `--otel`); each run emits
   a reproducibility manifest (model, index fingerprint, corpus namespace, seed, k,
   commit SHA); and the reliability contracts (F11=0, F13=0, leakage=0, mock≠headline,
   triad-gates-usefulness) are enforced as CI hard gates.
```

并在 README 文档表追加：

```markdown
| [SPEC_Q4_P6_P7](SPEC_Q4_P6_P7.md) | OpenInference/OTel trace exporter, run manifest, and CI hard-gate spec |
```

------

## 3. tag

```text
git tag -a v3.0-q4-reliability -m "<release notes>"
release notes 要点（据实，含诚实定语）：
  - Q4 把 Q3 动作选择负结果翻成正结果：rule 控制器 anti-gaming triad False→True on 留出 ops_test
    （precision@authorized 0.4545→0.6471、over_escalation→0.05、F11=F13=0、阈值冻结、validator 零改）；
    real but thin（过 ~1 case），两 run 迭代 + test query 修复 + 语料局限均已披露。
  - Track B：OpenInference/OTel 导出器（opt-in）+ run manifest + CI 硬门。
  - 安全地板自 v2.0 起字节级未变。
```

------

## 4. 验收（Q4 完结 = v3.0）

```text
[ ] P6/P7 全绿且 q4-p5 summary 过 CI 硬门
[ ] README 观测/CI 行 + 文档表条目已加（P6/P7 之后）
[ ] ROADMAP §11 全 ✅
[ ] tag v3.0-q4-reliability 指向 P6/P7/P8 完成的 commit
[ ] ruff 干净；pytest 全绿；Q1–Q4 已冻结结果（含 q4-p5 数字）不变
```
