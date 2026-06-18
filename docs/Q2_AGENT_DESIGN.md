# Q2 Agent 设计文档（freeze-ready）

状态：**freeze-ready**。§9 开放问题已据 Phase 1/2 + C2-05 结果拍板；W7 设计冻结会确认即生效。
对应：ROADMAP §5（Phase 3），打包决议 **A（双控制器消融）+ C（pass^k）**；
**B（judge 运行时验证器）已撤**——Phase 2 无可用 judge（三候选 wrong_side 0/2，全部未过 G2+probe）。
前置依赖（均已结）：Phase 1 已冻结 `final_gated_calibrated`；C2-05 复测结论已出
（动作 c 砍，见 §9.1 与 `EVALUATION_REPORT.md` C2-05 节）。

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

动作空间冻结为 **a / b / d / e**（c 已砍，见下）。

| 动作 | 类型 | 触发诊断 | 参数 | 不变式 |
| --- | --- | --- | --- | --- |
| a `rewrite_query` | 检索类 | WEAK_RECALL | `rewritten_query` | 不改变用户意图；不引入 query 之外的新实体（规则校验：rewritten 中的实体 ⊆ query ∪ 检索摘要实体） |
| b `filtered_retrieval` | 检索类 | POLICY_CROWDING | `filters`（如 `status=active`、`exclude_doc_ids=[...]`） | filters 只能**收紧**，不得放宽 ACL/state 约束 |
| d `present_conflict_set` | 终结类 | CONFLICT | `conflict_doc_ids` | 列出双方 + citation，不给唯一结论（沿用 Q1 `report_conflict`；见 §2.1） |
| e `refuse_with_explanation` | 终结类 | 任意 | `reason` | 永远可用；PERMISSION_BLOCKED 下是唯一合法动作 |

~~c `version_scoped_retrieval`~~ **已砍**（§9.1）：C2-05 复测显示 F3 非 top-5 崩塌，
残余只是泛 sibling-ranking 混淆、非版本混淆，无专门理据。版本指代不明的 query
归入 POLICY_CROWDING（deprecated 邻居，走 b）或 WEAK_RECALL（走 a）。

检索类动作执行后，结果**必须重新通过全部 gates**（state → ACL → evidence），
与 Q1 二次检索的处理完全一致。

### 2.1 动作 d 的诚实边界（P3-09 revised）

`present_conflict_set` 与 Q1 `report_conflict` 门存在功能重叠：真实 pipeline 中，
active-active conflict 通常由下游 `refusal_controller` 直接覆盖；若 evidence 已充足，
`diagnose()` 会短路为 `NO_RECOVERY`，agent 不会进入 d。d 因此保留为统一归因框架内
的终结动作，但报告时必须标注其边界：它只在 conflict-detected 且 evidence-insufficient
的角落由 agent 触发，P3-09 revised 预检不把 d 当作主要能力读数。

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
                          AND 0 < clean_active_count < min_support_count
  WEAK_RECALL          → a / e
  NO_RECOVERY          → e
（VERSION_AMBIGUITY 枚举随动作 c 一并删除；版本指代不明归 POLICY_CROWDING 或 WEAK_RECALL）
```

failure_type → 合法动作的映射表是 validator 的执法依据，controller 无权越出。

### 3.1 多合法动作 = 消融决策点（承重项保障）

上面的单动作映射是**下限**。若每个诊断下只有一个恢复动作 + e，规则与 LLM
控制器几乎必然选一样 → 消融退化为乏味的"LLM=规则"平局，撑不起决议 A。
为此，**信号共现时合法动作集取并集，让控制器的"选择"真正有内容**：

```text
weak-recall 信号（top_rerank_score < floor 或 entity_miss）        → 使 a 合法
policy-crowding 信号（deprecated/restricted 邻居 ≥2 且 0 < clean < min_support） → 使 b 合法
两者同时出现                                                       → 合法集 = {a, b, e}
```

这就是消融需要的决策点：

- `rule_controller`：固定优先序（默认 **b > a > e**——先试更便宜的元数据过滤再
  上 LLM 改写；W7 用校准数据定值），确定性。
- `llm_controller`：读诊断后可不同选（如 query 缩写/口语化时选 a；clean 证据被
  邻居挤占时选 b）。**这一选择正是被消融的东西。**

约束不变：validator 仍只放行合法集（并集）内的动作，预算/不可绕 gate 规则照旧。

**P3-09 revised 调整**：真实检索预门不再设置"≥6 共现否则 HALT"硬门。预门改为
记录真实诊断分布（failure_type、legal_actions、信号值）和 weak_recall/action-a
触发面；若多动作共现结构性稀缺，则诚实报告稀缺，把决议 A 的主读数移到
weak_recall case 上的 rule vs LLM rewrite args 质量。

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
| 冲突组呈现 | 能（Q1 已有） | 动作 d 只是纳入统一归因框架 |

**明确不在 agent 范围**：C2-05 测出的 hard-negative 残余 sibling-ranking 混淆
（hn_error 0.11–0.39，rerank 最差 0.389）是**检索/重排质量**问题，两个相似文档
status 同为 active、非 policy/phrasing 残余，动作空间 a/b/d/e 不针对它。
它是独立的 reranker 研究线（Q2-P1 衍生 / Q3），不混入 agent 评测。

**冻结门槛**：若 Phase 1 校准后 false-refusal 子集 <8 条，则动作 b 的测试床
不足，按 §9.3 决策收缩范围。这是对"校准吃掉 agent 增益面"风险的显式防御。

## 8. 评测与归因（打包决议 A + C 落地处；B 已撤）

系统对比（全部 real run；3 系统 × k=3）：

```text
final_gated_calibrated                    （对照）
final_agentic_v2_rule                     （动作空间 a/b/d/e + 规则控制器）
final_agentic_v2_llm                      （动作空间 a/b/d/e + LLM 控制器）
```

**B 已撤**：Phase 2 无可用 judge，运行时不引入 LLM verifier；既有的结构性
`citation_valid`（rule-based，来自 citation_binder）继续作为唯一运行时引用检查。
无 verifier on/off 变体。若将来用更强模型 + C2-05 的 wrong_side 锚点重验出可用 judge，
再按本节增列 verifier 变体（Q3）。

测试床：校准后仍 false-refusal 的 external 子集 + obfuscated 15 条 +
定向新 case ≈10 条（残余场景出题，泄漏检查执行**双向边界**：
信息过多=泄漏，信息为零=不可检索，见 ADJUDICATION §6 教训）。
P3-09 revised 后，真实检索下 a/b 共现不再是放行硬门；它作为稀缺边界实证归档。
能力主读数改为 weak_recall/action-a 触发 case 上的 rule rewrite vs LLM semantic rewrite。

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

（B 已撤，无 verifier 专项报告。）

## 9. 开放问题裁定（已据 Phase 1/2 + C2-05 拍板）

1. **动作 c 去留 → 砍。** C2-05：F3 非 top-5 崩塌，残余为泛 sibling-ranking 混淆、
   非版本混淆，无专门理据。动作空间冻结为 a/b/d/e。
2. **llm_controller 模型 → DeepSeek（系统主模型）。** controller 做的是"选哪个恢复
   动作"的决策，不评判自己的答案质量，无 self-preference 问题。第二家族对比为可选
   增量（<¥20），不进核心。
3. **测试床规模 → 保留 W7 数据相关的应急线**：校准后 false-refusal 子集若 <8 条，
   动作 b 降级为 case study，评测重心移向 obfuscated（动作 a）。W7 用实际子集量确认。
4. **verifier 降级措辞 → N/A**（B 已撤）。
5. **OTel 导出 → 否**（默认；在求职触发器清单）。
6. **二次检索合并语义 → 以 Q1 orchestrator 现行实现为准**（实现时 Codex 核实是替换
   还是并集；若并集，须评估证据集合膨胀稀释 evidence 阈值的风险）——唯一留给实现期
   确认的细节，不阻塞冻结。

## 10. W7 冻结会剩余确认项（非阻塞）

- §3 POLICY_CROWDING 阈值的具体值（用 Phase 1 校准后数据定）；
- §3.1 rule_controller 共现优先序默认 b > a > e 的确认/调整；
- §3.1 真实检索下测试床 a/b 共现与 weak_recall/action-a 触发面的实际条数；
- §9.3 的测试床子集实际量；
- §9.6 的合并语义实现核实。
其余设计已冻结，可据此让 Codex 起 agent 骨架（诊断器 → 动作 a/b/d/e → 规则 controller）。
