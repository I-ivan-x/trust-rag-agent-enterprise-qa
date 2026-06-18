# P3-09/10 实现规格：最终消融 run（rule vs llm）+ pass^k

交给：Codex（run + 指标）+ Owner（执行真实 run）。出规格：Claude。
设计：`Q2_AGENT_DESIGN.md` §8。前置：P3-01~08 已落地。
**这是 Phase 3 第一个真正消耗 token 的任务。** 报告散文（P3-11）由 Claude 后补。

## 0. 零 token 诊断预检（先跑，不过不准花 token）

P3-08 的验证 gate 是**受控手搭**的（diagnose 逻辑层），**未证明真实检索会产生共现信号**。
P3-09 用真实检索，所以**必须先零 token 记录真实触发面**：

```text
1. ingest agent_residual + 建真实索引（--include-agent-residual）。
2. 对 obfuscated(15) + agent_residual(10) 跑真实检索（hybrid + rerank）→ first_pass → diagnose()。
3. 统计真实检索下 failure_type/legal_actions 分布、每 case 信号值，以及
   weak_recall 触发（action a 合法）的 case 数。
4. RECORD 不 HALT：预检结果写入 docs/ 或 run artifact，作为"决策点稀缺"实证附录。
```

若 weak_recall/action-a 触发数 <8：交回 Owner/Claude 决策是否补更难的 obfuscated case。
这不是调到 LLM 赢，只是确认 rewrite 对比有足够触发面；真实多动作共现稀缺则如实报告，
不再制造共现或用"≥6 否则 HALT"阻断记录。

## 1. 消融 run（真实 LLM，预门通过后）

系统（3 个）：

```text
final_gated_calibrated      对照（无 agent loop）
final_agentic_v2            动作空间 + 规则 controller
final_agentic_v2_llm        动作空间 + LLM controller
```

测试床（主）：`obfuscated`(15) + `agent_residual`(10) = 25 条。
（external 校准后 false-refusal 子集为可选次要床，token 紧张可不跑。）

**每条 case 重复 k=3**（pass^k）。预算：3 系统 × 25 × 3 = 225 答案调用
+ llm controller/rewrite 调用（≤2/case）≈ 总 350–500 次，约 ¥40–60。

## 2. pass^k（决议 C）

```text
pass^1   单次运行 grounded_correct 的比例（任一次）
pass^3   同一 case k=3 次全部 grounded_correct 的比例
run_consistency  k 次间 action_trajectory 的 chosen_action 序列一致率
```
rule controller 是确定性的，pass^k 差异主要来自答案生成的非确定性；llm controller
额外有 controller 决策的非确定性——两者的 pass^1 vs pass^3 落差本身是可靠性信号。

## 3. 指标（全部按系统分报，agent 归因并排 rule vs llm）

```text
- grounded_correctness（每系统；agent_residual 与 obfuscated 分开报）
- agent_attribution（P3-06，每系统）：per-action trigger/accept/success/false_recovery/ineffective
- llm vs rule 并排：同一动作的 success / false_recovery 对比 —— 决议 A 的核心读数
- llm fallback_rate（llm 系统）
- TF2/3/4；TF1 候选（不自动判）
- pass^1 / pass^3 / run_consistency（每系统）
```

落盘：`data/eval_runs/<run_id>/`（results/traces/summary，含 agent_attribution +
pass^k 块）；run_id 形如 `p3-09-agent-ablation`。

## 4. 诚实框架（写进 summary，散文 P3-11 定稿）

```text
- 任何结果都有效：llm 赢 / 平 / 输 rule，配 per-action 归因都是有信息量的诚实结论。
  项目论题是"测量 agent 何时/为何有用"，不是"agent 必须赢"。
- agent_residual 是受控合成床 → grounded 数字标注"controlled agent-ablation evidence，
  非 headline，非真实世界覆盖率"。永不并入 external headline。
- false_recovery 并排 rule vs llm 是关键：若 llm 的 false_recovery 高于 rule，
  说明 LLM 控制器在制造假恢复（选了动作但没真 grounded）——这比 grounded 总分更诊断。
- 若 llm fallback_rate 高 → LLM 大多退化成 rule，消融趋同，如实说明。
- n 小（25）：报计数 + 率，不做置信区间声称。
```

## 5. 验收

```text
- 预检：真实检索 diagnose 分布归档；weak_recall/action-a 触发数记录；不再 HALT。
- 消融 run 落盘：3 系统 × 25 × k=3；summary 含 agent_attribution + pass^k + 并排对比。
- ruff + pytest 全绿（指标/pass^k 计算逻辑有零 token 单测）；不破坏既有 214。
- agent_residual 不进 headline（断言）。
- token 实耗记录在 summary（llm_call_count 等）。
```

## 6. 不做

```text
- 不做 TF1 replay（仍只候选）。
- 不把 agent_residual grounded 当 headline / 简历主数字。
- 不制造共现；不为动作选择层调语料。rewrite 触发面不足时，只补真实糟糕措辞类 obfuscated case。
- 不改 controller/validator/动作空间；诊断阈值按 P3-09 revised 的 scarcity cleanup 执行。
- 散文结论留 P3-11（Claude）。
```

## 7. 执行提示（Owner）

- 预检零 token，先跑、贴诊断分布 + weak_recall 触发数给 Claude/Owner 审，再决定是否放行花 token 的消融。
- 真实 run 用 DeepSeek 主模型；llm controller 也用主模型（§9.2，无家族 guard）。
- 跑完贴 summary（grounded per系统 + agent_attribution 并排 + pass^k + fallback_rate），
  Claude 审核 + 写 P3-11 trajectory 报告散文。
