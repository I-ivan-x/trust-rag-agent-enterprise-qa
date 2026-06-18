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

**1d. rewrite 触发面预检（零 token，决定 Agent 能力主读数的床够不够）。**
决议 A 的真实看点是 **LLM 控制器的语义改写 vs 规则改写**（action a 的 args 质量，
不是动作选择）。但改写要先**触发**才能比。对 `obfuscated`(15) + `agent_residual`(10)
跑零 token diagnose，统计 **weak_recall 触发（action a 合法）的 case 数**。
- 若 ≥8 → 改写对比的床够，进 §2。
- 若 <8（obfuscated 太易、检索仍找到 gold）→ **Claude 补几条更难的 obfuscated case**
  （重缩写/术语错位/间接问法，使 gold 在不改写时真检索不到）。这**不是制造**——
  用户用糟糕措辞提问是真实现象，测 agent 改写能否救回是合法考验；诚实点在于
  "调到改写**触发**为止"而非"调到 llm **赢**为止"。补完重跑 1d 预检。

## 2. 修订消融 run（P3-09，真实 LLM；先开 Docker/Qdrant）

**不再要求共现 ≥6**。目的从"看 llm 是否赢 rule"转为**测真实数字佐证稀缺结论**：

系统：`final_gated_calibrated`（对照）/ `final_agentic_v2`（rule）/ `final_agentic_v2_llm`（llm）。
测试床：`obfuscated`(15，天然 action-a 决策点) + `agent_residual`(10)。每 case **k=3**。

### ★ 决议 A 主读数：LLM vs 规则的改写质量（Agent 能力的真实展示）

在 weak_recall（action a）case 上，rule 与 llm 都选 rewrite，**但 rewritten_query 不同**
（rule=`query_rewriter` 关键词；llm=语义生成）。这是消融**真正不平**的维度，作为头条：
```text
- 并排呈现每条 weak_recall case 的 rule 改写 vs llm 改写原文（qualitative，进报告）。
- 二次检索恢复：rule 改写 vs llm 改写各自的 second_pass gold 命中（doc_hit 改善）。
- grounded：rule 改写 vs llm 改写各自最终 grounded_correct。
- 结论任一方向都有效：llm 改写更好→真实 agent 能力亮点；打平→"语义改写未超关键词改写"
  的诚实结论。绝不调到 llm 赢。
```

其余指标（佐证稀缺 + 安全 + 可靠性）：
```text
- grounded_correctness 每系统：v2(rule/llm) vs 对照 calibrated —— agent 恢复循环帮没帮。
- rule vs llm 动作选择一致性：预期 ≈ 一致（多动作共现≈0 → 选择无分叉；分叉在 args/改写质量）。
- llm fallback_rate：llm 多少次真提议 vs 退化 rule。
- agent_attribution（P3-06）每系统：per-action success/false_recovery。
- pass^1 / pass^3 / run_consistency（决议 C）。
```
预算：多数 case 证据充足→无 agent loop→仅答案调用；refused→无调用。实耗约 ¥25–40。
run_id `p3-09-agent-ablation`。agent_residual grounded 标"controlled, 非 headline"。

## 3. P3-11 报告（Claude，run 后）

Phase 3 诚实 headline，三层（能力 + 安全 + 边界）：
```text
能力：双控制器在 weak_recall case 上比 LLM 语义改写 vs 规则改写——决议 A 的真实读数
      （rewrite args 质量，附改写原文并排 + second_pass 恢复 + grounded）。
安全：类型化动作空间、validator 不可绕、LLM 失灵端到端退化为 rule（已证明）、逐动作归因、pass^k。
边界：零 token 真实检索预门两次实证——多动作决策点(共现)结构性稀缺(好的检索→证据充足→
      无恢复余地)，故动作选择层 rule≈llm；与 Q1 F5、Phase 1 一脉相承，agent 边际价值真实而狭窄。
```
**展示的是"能造受控 agent、用它做真实改写决策、并严格证明其适用边界",不是"agent 提升了 X%"。**
能力(改写对比)给 Agent 味，安全/评测给工程深度，边界实证给判断力。后两者编得出,
"诚实的边界实证 + 端到端安全证明"编不出。

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
