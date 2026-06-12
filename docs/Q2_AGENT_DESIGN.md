# Q2 Agent 设计冻结文档（预稿）

状态：预稿。在 Q2-W7 设计冻结会上确认后生效；§9 列出冻结时必须拍板的开放问题。
对应：ROADMAP §5（Phase 3），打包决议 A（双控制器消融）+ B（judge 运行时化）+ C（pass^k）。
前置依赖：Phase 1 产出 `final_gated_calibrated` 基线；hard-negative 重写复测结论
（决定动作 c 去留，见 `HARD_NEGATIVE_ADJUDICATION.md` §5.5）。

------

## 1. 目标与非目标

目标：在 **calibrated 基线之上**，用诊断驱动的类型化动作空间，提升
"校准后仍 false-refusal 子集 + obfuscated split" 上的 grounded_correctness，
并以 trajectory 级归因量化每个动作的独立贡献。

非目标（继承 Q1 N-08 禁令并扩展）：

```text
多 agent / 角色扮演式协作
无界规划、自由工具循环
任何形式的 gate 绕过
跨请求记忆 / 多轮会话状态
答案内容的自我反思重写（B 的 verifier 只做"过/不过"判定，不迭代改写答案）
```

## 2. 动作空间（白名单，类型化）

| 动作 | 类型 | 触发诊断 | 参数 | 不变式 |
| --- | --- | --- | --- | --- |
| a `rewrite_query` | 检索类 | WEAK_RECALL | `rewritten_query` | 不改变用户意图；不引入 query 之外的新实体（规则校验：rewritten 中的实体 ⊆ query ∪ 检索摘要实体） |
| b `filtered_retrieval` | 检索类 | POLICY_CROWDING | `filters`（如 `status=active`、`exclude_doc_ids=[...]`） | filters 只能**收紧**，不得放宽 ACL/state 约束 |
| c `version_scoped_retrieval` | 检索类 | VERSION_AMBIGUITY | `version_constraint` | **条件性实现**：仅当 hard-negative 重写复测确认 F3 存在 |
| d `present_conflict_set` | 终结类 | CONFLICT | `conflict_doc_ids` | 列出双方 + citation，不给唯一结论（沿用 Q1 `report_conflict`） |
| e `refuse_with_explanation` | 终结类 | 任意 | `reason` | 永远可用；PERMISSION_BLOCKED 下是唯一合法动作 |

检索类动作执行后，结果**必须重新通过全部 gates**（state → ACL → evidence），
与 Q1 二次检索的处理完全一致。

## 3. 诊断 Schema

`DiagnosisReport`（由现有 gate 输出 + 检索邻域统计推导，纯规则，无 LLM 调用）：

```text
evidence_decision:        sufficient | insufficient
gate_signals:
  permission_blocked_count   被 ACL 拦截的 chunk 数
  deprecated_neighbor_count  邻域中 deprecated chunk 数
  restricted_neighbor_count  邻域中 restricted chunk 数
  conflict_group_ids         检出的 active-active 冲突组
  clean_active_count         干净可用证据 chunk 数
retrieval_quality:
  top_rerank_score
  support_chunk_count
  entity_miss                query 实体未命中标记
failure_type（派生枚举，决定合法动作集）:
  PERMISSION_BLOCKED   → 仅 e
  CONFLICT             → d / e
  POLICY_CROWDING      → b / e        触发条件（具体化，阈值 W7 冻结）：
                          (deprecated_neighbor_count + restricted_neighbor_count) ≥ 2
                          AND clean_active_count < min_support_count
  VERSION_AMBIGUITY    → c / b / e    （c 未实现时退化为 b）
  WEAK_RECALL          → a / e
  NO_RECOVERY          → e
```

failure_type → 合法动作的映射表是 validator 的执法依据，controller 无权越出。

## 4. Controller 双实现（打包决议 A）

同一输入（DiagnosisReport + query + 邻域摘要），两个实现：

1. `rule_controller`：确定性查表（§3 映射表 + 固定优先序），零 LLM 调用。
2. `llm_controller`：LLM 结构化输出 `{action, args, reason}`；
   模型用系统主模型（DeepSeek），temperature=0。
   解析失败或被 validator 拒绝 → **fallback 到 rule_controller 的选择**。

消融对比是本设计的核心交付：`final_agentic_v2(rule)` vs `final_agentic_v2(llm)`
在完全相同的动作空间、约束、测试床上对比。LLM 控制器输掉是可接受结论。

## 5. Validator（代码强制，不可配置关闭）

```text
V1  action ∈ 当前 failure_type 的合法动作集（§3 映射表）
V2  非终结动作预算：每条轨迹最多 2 个
V3  PERMISSION_BLOCKED 诊断下只接受 e
V4  filters 只收紧不放宽（白名单字段 + 方向校验）
V5  rewrite 实体约束（§2 不变式，规则校验）
V6  检索类动作结果强制重过全部 gates
V7  非法提议：拒绝 + trace 记录 + fallback（llm_controller → rule 选择；rule 不会非法）
```

最坏情况下 `llm_controller` 行为完全退化为 `rule_controller`——
这是"LLM 进决策环但安全性不依赖 LLM"的结构保证。

## 6. 停止条件与轨迹不变式

```text
终止：执行终结动作（d/e）或检索类动作后 evidence sufficient → answer
预算：非终结动作 ≤2 ⇒ 轨迹长度 ≤3 步
不变式：每条轨迹必终结于 answer / refuse / conflict-set；无循环；
        同一动作类型同一轨迹内不重复执行（防 rewrite-rewrite）
```

## 7. 残余场景论证（为什么 calibrated gate 之后 agent 仍有空间）

| 场景 | 静态校准能否处理 | 需要 agent 的原因 |
| --- | --- | --- |
| deprecated 邻居挤占但 clean 证据存在 | **大部分能**（Phase 1 策略变体） | 校准吃掉多少，W7 用数据确认；剩余的需 query 相关的 exclude 列表（动作 b） |
| query 用缩写/口语，首轮召回弱 | 不能（与 gate 无关） | 需 query-dependent 改写（动作 a，obfuscated split 实测） |
| query 版本指代不明（"现在的限流规则"） | 不能 | 需从 query 推断版本意图（动作 c，条件性） |
| 冲突组呈现 | 能（Q1 已有） | 动作 d 只是纳入统一归因框架 |

**冻结门槛**：若 Phase 1 校准后 false-refusal 子集 <8 条，则动作 b 的测试床
不足，按 §9.3 决策收缩范围。这是对"校准吃掉 agent 增益面"风险的显式防御。

## 8. 评测与归因（打包决议 A + B + C 落地处）

系统对比（全部 real run）：

```text
final_gated_calibrated                    （对照，verifier 关）
final_agentic_v2_rule                     （动作空间 + 规则控制器，verifier 关）
final_agentic_v2_llm                      （动作空间 + LLM 控制器，verifier 关）
优胜控制器 + verifier 开                   （B 专项；不做全交叉，系统变体封顶 4 个）
```

测试床：校准后仍 false-refusal 的 external 子集 + obfuscated 15 条 +
定向新 case ≈10 条（残余场景出题，泄漏检查执行**双向边界**：
信息过多=泄漏，信息为零=不可检索，见 ADJUDICATION §6 教训）。

逐动作归因表（每动作独立报告，不混入总指标）：

```text
trigger_count          诊断给出该动作机会的次数
accept_count           controller 选择且 validator 放行的次数
success_count          执行后 insufficient→sufficient 且最终 grounded 的次数
false_recovery_count   执行后看似有证据但 grounded 失败的次数
```

可靠性（C）：每 case 重复 k=3，报告 pass^1 与 pass^3 及跨运行动作序列一致率。

trajectory 失败分类（扩展 F-taxonomy）：

```text
TF1 选错动作（事后归因：另一合法动作在重放中成功）
TF2 无效动作（执行了但证据无改善）
TF3 validator 拒绝（llm_controller 提议非法）
TF4 预算耗尽仍不足
```

B 的专项报告：verifier 开启的 grounded 变化 vs 每答案延迟/成本增量
（judge 模型沿用 Phase 2 选型，必须非 DeepSeek 家族）。

## 9. 冻结时必须拍板的开放问题

1. 动作 c 去留：以 hard-negative 重写复测结果为准（F3 成立→实现；否则砍）。
2. llm_controller 的模型：默认系统主模型（DeepSeek）；是否值得加第二家族对比，
   视 token 预算（预计可加，<¥20）。
3. 测试床规模：校准后 false-refusal 子集若 <8 条，动作 b 降级为 case study，
   评测重心移向 obfuscated（动作 a）。
4. verifier 不过线的降级措辞：直接 refuse vs 弱化为"低置信answer + 警示"——
   倾向前者（保持 fail-closed 一致性），冻结时确认。
5. trace 新字段是否同步做 OTel 导出：默认否（已移入求职触发器清单）。
6. 二次检索结果与首轮的合并语义：替换还是并集——以 Q1 orchestrator 现行实现为
   基准确认后写死；若取并集，必须评估"证据集合膨胀稀释 evidence 阈值"的风险。
