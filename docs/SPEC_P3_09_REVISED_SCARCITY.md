# P3-09 修订 + Phase 3 诚实收口（接受决策点稀缺）

交给：Codex（清理 + 消融 run）+ Owner（执行真实 run，先开 Docker/Qdrant）。
出规格：Claude。背景：零 token 预门两次证明真实检索下 agent 多动作决策点 ≈0
（结构性：好的检索找到 gold → 证据充足 → 无恢复余地）。Owner 已裁定：**接受稀缺为
诚实结论，不制造数据。**

## 1. 诚实清理（Codex，零 token）

让"agent 有 4 个动作"的声称变准确，而不是含死代码/冗余动作：

**1a. 修 `policy_crowding` 退化阈值（真 bug，与 W7 无关）。**
现状 `clean_active < 1`（=0 才触发）→ action b 只在"没有干净证据"时触发，而那时过滤无用
= **死代码**。改为有原则的带：`0 < clean_active < min_support`（min_support 占位默认 ≥2，
注释 TODO-W7）——即"有一些干净证据但低于充足线、被 deprecated/restricted 挤占",
这才是 filtered_retrieval 能救的场景。**注意**：本 corpus 的 gold 真实检索排第一、
clean_active 始终 ≥ 充足线，所以修完此 split 仍不触发 b——这是接受的稀缺事实，
不为它再调；修复目的是让 b 在**未来真实场景**里是活代码 + 让 §3 报告诚实。

**1b. 处理 action d（AR-010 澄清的连带）。**
Codex 已确认：conflict 由下游 `refusal_controller` 覆盖，证据充足时 diagnose 短路、
agent 看不到动作 d。**两选一，Owner/Claude 倾向后者**：
  - 从 agent 动作空间移除 d（承认冗余）；**或**
  - 保留 d 但在 `Q2_AGENT_DESIGN.md` + 报告**显式标注**"d 与 Q1 report_conflict 门冗余，
    仅在 conflict-detected-且-evidence-insufficient 的边角才由 agent 触发，实测未出现"。
  倾向**保留 + 标注**（不改已测代码，诚实记录边界）。

**1c. 重跑零 token 预门，RECORD 不 HALT。**
去掉"≥6 否则 HALT"硬门，改为**记录真实诊断分布**（每 case failure_type/legal_actions/
信号值）写入 `docs/` 或 run artifact，作为"决策点稀缺"的实证附录。预门从"放行门"
转为"实证记录"。

## 2. 修订消融 run（P3-09，真实 LLM；先开 Docker/Qdrant）

**不再要求共现 ≥6**。目的从"看 llm 是否赢 rule"转为**测真实数字佐证稀缺结论**：

系统：`final_gated_calibrated`（对照）/ `final_agentic_v2`（rule）/ `final_agentic_v2_llm`（llm）。
测试床：`obfuscated`(15，天然 action-a 决策点) + `agent_residual`(10)。每 case **k=3**。

测什么（全部诚实记录，任何结果有效）：
```text
- grounded_correctness 每系统：v2(rule/llm) vs 对照 calibrated —— agent 恢复循环到底帮没帮
  （预期：小或无增益，与 Q1 F5 一致）。
- rule vs llm 轨迹一致性：预期 ≈ 完全一致（共现≈0 → 控制器无分叉点）。这是"决策点稀缺
  → 控制器选择鲜有分叉"的直接佐证，不是失败。
- llm fallback_rate：llm 多少次真提议 vs 退化 rule。
- agent_attribution（P3-06）每系统：per-action success/false_recovery。
- pass^1 / pass^3 / run_consistency（决议 C）。
```
预算：多数 case 证据充足→无 agent loop→仅答案调用；refused→无调用。实耗约 ¥25–40。
run_id `p3-09-agent-ablation`。agent_residual grounded 标"controlled, 非 headline"。

## 3. P3-11 报告（Claude，run 后）

Phase 3 诚实 headline，不是"llm 赢"，而是：
```text
"完备且安全的有界 agent 已构建并实测：类型化动作空间 a/b/(d 冗余)/e、规则与 LLM 双控制器
(LLM 失灵时确定性退化为 rule,已端到端证明)、validator 不可绕、逐动作归因、pass^k 可靠性。
经零 token 真实检索预门两次实证:多动作决策点在真实检索下结构性稀缺(共现≈0,因好的检索
使证据充足、无恢复余地),故双控制器选择鲜有分叉、rule≈llm。这与 Q1 的 agentic 零增益(F5)、
Phase 1 的 over-refusal 策略驱动一脉相承——agent 的边际价值真实而狭窄。"
```
这是三支柱 Agent 维度的最终结论:**展示的是"能造受控 agent 并严格证明其适用边界",
不是"agent 提升了 X%"。** 后者编得出,前者编不出。

## 4. 验收

```text
- 1a/1b/1c 落地;预门改 RECORD,诊断分布归档;ruff+pytest 绿(不破坏既有 214)。
- p3-09-agent-ablation 落盘:3 系统 × 25 × k=3;grounded/attribution/pass^k/fallback_rate/
  rule-vs-llm 一致性全报;agent_residual 不进 headline(断言)。
- token 实耗记录。
- 真实 run 前开 Docker/Qdrant(否则 keyword-only 降级,vector_index_built 须=true)。
```

## 5. 不做

```text
- 不制造共现/不调语料逼 agent 看起来有用。
- 不把 agent_residual grounded 当 headline/简历主数字。
- TF1 仍只候选不 replay。
- 散文结论留 P3-11(Claude)。
```
