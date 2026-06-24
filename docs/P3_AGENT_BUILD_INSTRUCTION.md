# P3 Agent Build Instruction（给 Codex 的执行指令）

状态：执行版。配套 `ROADMAP.md` §5（Phase 3）与 `Q2_AGENT_DESIGN.md`（freeze-ready）。
定位：选项 1 —— 保住不可砍底线（双控制器消融 A + 逐动作归因 + pass^k），
对比 run 节流，**Phase 3 做成「严格证伪 agent 增益 + 机制可靠性 + 残余失败归因」**，
而非「发现 agent 增益」。

## 0. 前提

P3-09 零 token 诊断已先验证实：校准后系统上 agent 有效残余面 ≈ 0
（a legal trigger=2；b legal trigger=0、gold-doc-recoverable=0；d legal trigger=0）。
这是 ROADMAP §8 已预案的「校准吃掉增益面 → 零增益诚实归档」路径，**不是进度落后**。

## 0.1 P3-09 诊断对设计的回填（先确认，再开工）

- `Q2_AGENT_DESIGN.md` §10 W7 确认项第 3 条（a/b 共现与 action-a 触发面实际条数）
  现已有答案：**a=2、b 共现=0、d=0**。请在设计文档 §10 标注此项已结。
- 设计 §3.1 的「{a,b,e} 共现消融决策点」在真实测试床上不成立（b legal=0）；
  双控制器消融(A)退化为 `a vs e`（n=2）。A 仍要实现（不可砍底线），但其结论
  在报告中必须标注为**定性、n 极小、统计无力**，主读数走 §3.1 fallback
  （那 2 条 weak_recall case 上 rule rewrite args vs LLM semantic rewrite args 的质量对比）。
- §3.3 POLICY_CROWDING 阈值、§3.1 优先序 b>a>e：按 Phase 1 校准数据确认即可，不阻塞骨架。

## 1. 全局红线（每个任务都适用）

1. 动作空间冻结 **a/b/d/e**（c 已砍）；不得新增动作类型。
2. **validator 硬约束**（设计 §5 V1–V7）：合法集执法、非终结动作预算 ≤2、
   PERMISSION_BLOCKED 仅 e、filters 只收紧不放宽、rewrite 实体 ⊆ query∪检索摘要、
   检索类动作结果**强制重过全部 gates**、非法提议拒绝+trace+fallback。
3. **任何动作不得绕过 ACL/state gate**；动作 b 的过滤器只能收紧，restricted/deprecated
   不得因过滤重入。
4. **agent_residual / AR-* / AR-H* 是自产 synthetic 诊断 split，永不进 external headline**，
   summary 必须 `headline_eligible=false` 且标 diagnostic-only。
5. **不注水**：不得为提高触发率新增/改写 case。AR-H01..H08 的 0 触发是结论不是 bug，
   测试床冻结在当前规模。
6. 零增益是合法结论，按「现象→根因→下一步」三段式归档，不美化。
7. P3-01~P3-06 以单测为主、mock provider、零/低 token；真实 token 只花在 P3-09。
8. 不改 `Q1_HARD_DEMO_TASK_PLAN.md`；不打印 API key；`data/eval_runs/*` 维持 gitignore。

## 2. 机制实现（P3-01 ~ P3-06，近零 token）

**P3-01 诊断提取器**：把 P3-09 precheck 的诊断逻辑产品化为 `DiagnosisReport`
（设计 §3 schema）：gate 输出+邻域统计 → failure_type ∈
{PERMISSION_BLOCKED, CONFLICT, POLICY_CROWDING, WEAK_RECALL, NO_RECOVERY} + 合法动作集（并集语义，§3.1）。
- 验收：单测覆盖五类 failure_type；对当前 33 条诊断输出与 P3-09 报告逐 case **一致**（回归锚点）。

**P3-02 动作 b（filtered_retrieval）**：复用检索栈 + 元数据过滤器，只收紧。
- 验收：单测证明 restricted/deprecated 不因过滤重入；二次检索后 ACL/state gate 仍生效；
  `gold-doc-recoverable` 计数与 P3-09 一致（预期 0，作回归断言）。

**P3-03 规则 controller**：诊断 → 合法集内固定优先序（默认 b>a>e）选动作，预算≤2，确定性。
- 验收：全分支单测；无合法恢复动作时落 e。

**P3-04 orchestrator 集成 + trace 新字段**：动作序列、预算消耗、validator 拒绝记录、
每动作 trigger/outcome；停止条件不变式保留（§6：轨迹≤3 步、无循环、同类型动作不重复）。
- 验收：agentic loop 测试更新；Q1/Q2 现有测试不回归。

**P3-05 LLM controller + validator（双控制器消融 A，不可砍）**：结构化输出
`{action,args,reason}`，DeepSeek temperature=0，解析失败/被拒 → fallback rule controller。
- 验收：mock LLM 单测覆盖「合法执行 / 非法被拒退化 / 预算超限截断」；零真实 token。

**P3-06 逐动作归因进 runner/metrics**：每动作独立报
`trigger_count / accept_count / success_count / false_recovery_count`（设计 §8）。
- 验收：metrics 单测；归因字段写入 summary schema；不混入总指标。

## 3. 最小真实对比 run（P3-09 ~ P3-10，节流）

- 系统 3 个：`final_gated_calibrated` / `final_agentic_v2_rule` / `final_agentic_v2_llm`（无 verifier，B 已撤）。
- 测试床 = **仅 legal-trigger 子集**（a 的 2 条 + 任何 b/d 触发）+ 校准后 external 仍 false-refusal 子集 + obfuscated。**不含 hard-negative**（设计 §7）。
- k=3，产出 pass^1 + pass^3 + 跨运行动作序列一致率。
- **预算硬上限**：子集极小，≈3 系统 × ~6 case × k=3 ≈ 50–80 calls（¥10 量级）。
  legal-trigger case 不足也照跑不补，报告写明「n 不足以做百分比，结论为定性证伪」。
- 验收：summary `headline_eligible` 受代码合约保护；真实 final run 确认
  `vector_unavailable=false` 实际写出（补 P1-08 产物侧尾巴）；`expected_rewrite_used=false`；
  mock_used=false；toy_retrieval=false。

## 4. 报告（P3-11，三段式）

trajectory 归因 + 可靠性报告，核心结论预写：
- **现象**：agent 动作 a/b/d 有效触发面≈0（P3-09 零 token 诊断 + 最小真实 run 双证据）。
- **根因**：残余 false-refusal 是 policy 裁决型（F1/F2），非检索可救型（b surface=25 但 gold-doc-recoverable=0；动作 b 不绕 gate 故救不回）。
- **下一步**：残余面消失是 Phase 1 校准的合理后果；agent 结论为「机制可用、当前测试床无可测增益」；可能释放空间的方向（版本指代消歧等）留 Q3。
taxonomy 扩展 TF1–4（选错动作/无效动作/validator 拒绝/预算耗尽）。
叙事约束：ROADMAP §0 第三句每从句指得到 run_id；**不得从 2~6 条 case 算增益百分比当卖点**。

## 5. 最终验收清单（Phase 3 收口前）

```
[ ] P3-01~P3-06 单测全过，主链不回归（pytest 全量绿）
[ ] 动作 b 不绕 ACL/state（单测：restricted/deprecated 不重入）
[ ] LLM controller 非法提议被拒+退化（单测）
[ ] 逐动作归因 trigger/accept/success/false_recovery 落 summary
[ ] P3-09 最小对比 run：3 系统 × k=3，headline_eligible 合约生效，vector_unavailable=false 实测写出
[ ] pass^1 与 pass^3 并报
[ ] agent_residual/AR-* 全程 diagnostic-only，headline_eligible=false
[ ] 报告三段式，零增益诚实归档，无 case-level 百分比卖点
[ ] 双控制器消融结论标注「定性、n 极小」（§0.1）
[ ] ruff + pytest 绿；零 token 部分确认零 token；真实 run token 在 ¥10 量级
[ ] .env / Q1 Task Plan 无 diff
```

## 6. 分批执行（一次一批，每批审完再下一批）

- ✅ **第 1 批（commit `74e7638`）**：P3-01 诊断器 + P3-02 动作 b + P3-03 规则 controller +
  P3-04 orchestrator 集成。全单测/mock/零 token；pytest 246 passed。
- ✅ **第 2 批（commit `c7f632b`）**：P3-05 LLM controller（temperature=0 + 四类 fallback→rule）
  + P3-06 逐动作归因（trigger/accept/success/false_recovery_count，不混入总指标）。
  零真实 token；pytest 247 passed。
- ⏸️ **第 3 批（推迟，下周）**：P3-09 最小对比 run + P3-10 pass^k + P3-11 报告。
  唯一花真实 token（¥10 量级）；**需 Owner 放行 token 后再执行**。

建议 commit（每批一个）：
```
agent: phase 3 batch 1 — diagnosis extractor, filtered_retrieval, rule controller, orchestrator
```
