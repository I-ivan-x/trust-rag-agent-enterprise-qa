# Roadmap: Q1 收尾 + Q2 执行计划

版本：v1.0-q2-roadmap
状态：冻结执行版（替代 `Q1_HARD_DEMO_TASK_PLAN.md` §28 的 Q2 草案；不修改已冻结的 Q1 计划本体）
执行模式：沿用 Q1 —— Codex 单代码执行者，Claude 非代码协作者，Owner 验收
变更纪律：本计划冻结后只在 Q2-W7 期中检查点按预设砍序收缩，不再增项

------

## 0. 叙事目标

Q2 结束后，项目必须支撑以下三句话，且每个从句对应至少一份真实 run 数据：

```text
Agent 工程：
  agent 在受约束的类型化动作空间里运行，LLM 策略与规则策略做过同条件消融，
  每个动作有 trajectory 级归因，可靠性按 pass^k 报告。

Eval 工程：
  claim-support 判官经人工锚点验证，并与 RAGAS / DeepEval 做过同锚点 agreement 对比；
  评测以回归门禁形式进入 CI。

AI 治理：
  四道 trust gate 之外，系统对 indirect prompt injection（OWASP LLM01）做过实测；
  所有 headline 数字受 headline eligibility 代码合约保护。
```

继承 Q1 的两条铁律：

1. headline 只引用真实 run 产出的数字；judge-based 指标必须带 `judge_based` 标签，
   永不与人工审计数字混写。
2. 负结果照常进报告和 failure taxonomy，按"现象 → 根因 → 下一步"三段式归档。

------

## 1. Q1 瘦收尾（2 周）

原计划 Week 7/8 压缩执行。任务三分法：保留完整性层、推迟包装层、砍掉低值项。

### 1.1 收尾第 1 周

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| C1-00 | Codex | **审计前置补丁**：run 产物持久化 answer_text / claims / supporting_chunk_ids，并复跑 final_agentic real（**仅 external + obfuscated，≈65 次调用**；hard_negative 不复跑——模板 query 的答案无审计语义，该层推迟至重写后，见 C2-05）。Week 6 产物未存 claim 级内容，已实测确认（`CITATION_AUDIT_GUIDE.md` §0） | 复跑 run 落盘，audit 引用新 run_id |
| C1-01 | Codex + Owner | ✅ 冻结 15 条 census 抽样并完成两遍标注：GPT pass（preview，`judge_pass_v1_gpt_labels.jsonl`）+ **人工盲标 census**（`manual_audit_v1_labels.jsonl`，annotator=owner，2026-06-14）。实测可审 claim = 15（每 case 1 claim），按 census 全收，非抽样。 | 人工结果：11 supported / 4 weak / 0 unsupported / 0 wrong_side；human-vs-GPT exact agreement 15/15（easy split，n=15，非 validated judge，写入 CITATION_AUDIT.md） |
| C1-02 | Codex | ✅ Dockerfile / docker-compose / Makefile / smoke_test 已落地：compose 默认 mock provider，API + 内部 Qdrant 可启动；`scripts/smoke_test.py` 可在容器内准备 sample index 并打 `/health` + `/chat` | 已验：`docker compose up -d --build` + `docker compose exec -T api python scripts/smoke_test.py --prepare --embedding-provider mock --require-vector --chat` 通过；模型权重通过 `huggingface_cache` volume 挂载 |
| C1-03 | Claude + Codex | ✅ README 已按新信息架构定稿：Honest Results 正负双表、Evaluation Governance、Docker Quick Start、F1–F8/报告链接 | 第一屏含正负结果并排表；禁放数字清单见 §1.4 |
| C1-04 | Owner | ✅ hard-negative 裁定已落地：F8 确认为 Week 6 hard-negative 主因；F3 未被原 20 条模板 query 有效测试。C2-05 已用 Owner 签字 query 收缩为 18 条并完成零 token retrieval-only 复跑。 | 结论已写回 `FAILURE_ANALYSIS.md` / `EVALUATION_REPORT.md`；Phase 3 动作 c 理据转弱 |

### 1.2 收尾第 2 周

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| C2-01 | Owner | ⏭️ **可选,不再阻塞**。人工 census 已一遍完成(C1-01),真正的人工自一致性(Owner vs ≥7 天后盲复标)降为可选;此 easy split 上预计也接近 100%,信息量低。Phase 2 judge 选型改用 G2 绝对门(≥0.80),不依赖 G1 自一致率锚。 | 如做:`manual_audit_v1_relabel.jsonl` |
| C2-02 | Claude | ✅ 人工审计结果已写入 `CITATION_AUDIT.md`（human census + human-vs-GPT 一致率 + caveats）；`EVALUATION_REPORT.md` 两处 non-blocking 项已补（hard-negative retrieval 行 0.05、fixture mock 免责句）。 | 完成 |
| C2-03 | Claude | `TECHNICAL_DESIGN.md` 瘦版：ADR 体例，6–8 条决策记录，每条含 Decision / Rationale / Measured consequence / Calibration path | 四个 Q1 负结果各回溯到一条 ADR；体例 append-only，Q2 演进只增不改 |
| C2-04 | Owner | ✅ tag `v0.3-q1-hard-demo` + release notes | Q1 正式收口；tag 指向包含 Docker/README/评估报告补丁的 release commit |
| C2-05 | Claude + Codex | ✅ **hard-negative 重写落地**：`hard_negative_rewritten_v1` 18 条；旁路 annotation；双向泄漏检查 18/18 通过；gold 校验通过；零 token retrieval-only run `q2-c205-hardneg-rewritten-retrieval` 落盘。 | doc_hit@5：四档检索均 1.0000；F8 确认，F3 不成立为 top-5 检索崩塌；rewritten real run 降为可选 citation/answer 审计 |

### 1.3 砍掉与推迟

```text
砍掉：API_SPEC 完整版（Swagger 自描述）；集成测试"全覆盖"（收窄为 chat + eval 关键路径）。
推迟（求职触发器清单，见 §6）：DEMO_VIDEO_SCRIPT、RESUME_BULLETS、PROJECT_REVIEW、
  INTERVIEW_QA 扩充、DEMO_SCRIPT 精修。
```

### 1.4 README 数字纪律（摘要）

可放（带定语）：false_answer_rate 0.00；citation_valid 1.00（structural）；
doc_hit@5 0.60→0.80（vector→hybrid）；direct_llm raw 0.20 / grounded 0.00（污染信号）；
grounded 0.24 必须与 false_refusal 0.46 成对出现；hard_negative_error_rate 1.0 与
agentic 0.3333=0.3333 放 "What fails" 表并各配根因一行。

禁放：rerank 提升；任何 "citation accuracy"；raw_correctness 单独出现；
fixture mock 数字；裸 "24% accuracy"。

------

## 2. Q2 总览（13 周，三支柱）

| 支柱 | 交付 | 周次 |
| --- | --- | --- |
| Eval 工程 | gate calibration + trade-off 曲线；人工锚定判官三方对比；CI 回归门禁 | W1–W6 |
| AI 治理 | injection/poisoning 红队 split（10 条）实测 | W6–W7 |
| Agent 工程 | 类型化动作空间 + 双控制器消融（A）+ judge 运行时化（B）+ pass^k（C） | W7–W13 |

### 2.0 Eval split 架构（purpose-separated；冻结此原则）

一个 split 一个目的，不互相膨胀。目标→split 映射 + 状态：

| 目标 | split | 状态 |
| --- | --- | --- |
| hard-negative 检索复测（query 是否唯一指向 gold） | `hard_negative_rewritten_v1`（18 条） | ✅ C2-05 完成；只做检索/引用诊断，不塞别的；首个有效测量为 `q2-c205-hardneg-rewritten-retrieval` |
| Indirect injection / poisoning（治理） | injection split（10 条） | **已规格**：`REDTEAM_INJECTION_SPLIT.md`（P2-07）。**勿重造** |
| Agent 动作空间残余场景 | agent 定向 case（≈10 条） | **设计已 freeze-ready**：`Q2_AGENT_DESIGN.md`（动作 c 已砍 → 空间 a/b/d/e；§9 全部裁定）。C2-05 已结，不再阻塞；W7 确认子集量后出题（针对动作 a/b 的残余场景） |
| Judge / 人工判别力 wrong_side probe | `judge_probe_wrong_side_v1`（5–6 条） | **新增**（采纳外部分析）。源自 hard-neg similar_title 对（天生 wrong_side 素材）；补 judge harness 当前 wrong_side 0/2 缺口。**延后到 judge 重试时做**，每条配 wrong_side_answer_example |
| ACL / deprecated 边界 | policy_boundary | **缓做**：与 external/fixture 现有 permission_denied/deprecated case 重叠，边际低 |

诊断标注（gold_distinguishers 等）一律走旁路 annotation 文件，**非评分**，不进 query/检索打分路径（避免再造未验证的 rule-based judge）。

```text
W1–2   evidence gate 参数化 + 阈值 sweep
W3     策略变体 + 复跑 + trade-off 曲线 → 冻结新基线 final_gated_calibrated
W4–5   judge：人工锚点 × {RAGAS, DeepEval, 自建} agreement 对比 + 选型
W6     judge 接入 metrics + 最小 CI 门禁 ∥ 红队 split 构造（10 条）
W7     红队 run + 报告 ∥ agent 设计冻结 ★ 期中 scope review
W8–9   agent 核心：诊断器 → 动作 a/b/d/e（c 已砍）→ 规则 controller → orchestrator 集成
W10    LLM controller + validator（A）+ 逐动作归因
W11    （B 已撤——无运行时 verifier；W10 富余并入 LLM controller 调优/归因）
W12    最终对比 run（3 系统 × k=3，产出 pass^k，C 在此合并）
W13    trajectory 归因报告 + 可靠性报告 + 文档更新 + tag
```

### 2.1 关键依赖链（顺序不可换的原因）

```text
人工 citation audit（Q1 收尾）
  → judge 锚定验证（W4–5）        锚点就是验证集
    → judge 运行时化（W11）        未验证的判官不得当门卫

gate calibration（W1–3）
  → agent 全部工作（W8+）          agent 对照基线必须是 calibrated 版，
                                   否则增益归因与校准混淆；且校准释放
                                   evidence-insufficient 触发面后 agent 才有出场机会
```

红队 split 无依赖，用 W6–W7 的等待间隙填缝（split 构造主要是语料/出题工作，
与 judge 代码工作并行不抢执行者）。

------

## 3. Q2 Phase 1：Gate Calibration（W1–3）

目标：把 Q1 最大已测失败（false_refusal 0.46 / refusal 0.74）转化为校准数据与新基线。

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| P1-01 | Codex | evidence gate 阈值参数化 + sweep harness | 单命令跑 4–6 个配置点 |
| P1-02 | Codex | ✅ 阈值 sweep：external × final_gated × 5 配置；旧 `q2-p1-02-legacy-threshold-sweep` 因 Qdrant collection 缺失实际为 keyword-only fallback，已用 `q2-p1-02-legacy-threshold-sweep-reconciled` 重跑 | 每点输出 false_refusal / false_answer / grounded；corrected default = 0.46 / 0.00 / 0.24 |
| P1-03 | Codex | **策略变体**：区分"检索邻域存在 deprecated/restricted 邻居"与"仅剩 deprecated/受限证据"两种 gate 决策 | 新旧策略均有单测；F1/F2 场景行为差异可演示 |
| P1-04 | Codex | ✅ 策略变体复跑 external full；旧 `q2-p1-04-neighbor-tolerant-default` 因 vector unavailable + 权限泄漏不得入 baseline，P1-07 后用 `q2-p1-07-neighbor-tolerant-fixed` 重跑 | fixed neighbor_tolerant：false_refusal 0.44 / false_answer 0.00 / grounded 0.22 |
| P1-05 | Claude | ✅ 完成（随对账修正）。trade-off 报告在 EVALUATION_REPORT "Q2 Phase 1" 节。**修正后结论**：(1) 阈值旋钮惰性——reconciled 全 5 点中 4 点全等（0.46/0.00/0.24），仅 min_score=1.0 退化为全拒答；over-refusal 非阈值驱动而是 policy 驱动（证实 F1/F2）；(2) neighbor_tolerant 修复后（q2-p1-07）相对 legacy 几乎不释放拒答（fr 0.46→0.44）且 grounded 略低（0.24→0.22），不进 baseline。原 q2-p1-04 的 0.08/0.22"权限泄漏"是 keyword-only 坏跑 + 未修策略复合产物，已作废。独立核验：reconciled/p1-07 真值经 results.jsonl 重算确认。 | 已落盘 |
| P1-06 | Owner | ✅ 冻结 `final_gated_calibrated` = legacy default（非 neighbor_tolerant；min_support_count=1/min_score=none；ref run `q2-p1-02-legacy-threshold-sweep-reconciled/default`；cross-check `q2-p1-06-reconciled-legacy-default`）。对账结论：0.28/0.34/0.62 来自 Qdrant collection 缺失导致的 keyword-only fallback，不是 P1-01 调松默认；恢复向量栈后精确复现 Week 6 0.24/0.46/0.74。 | 已冻结为保守对照，不宣称相对 Week 6 增益 |
| P1-07 | Codex | ✅ **策略修复（P1-05 衍生）**：neighbor_tolerant 须区分"受限的是邻居"与"受限的是答案所需证据"，后者仍拒答；修复前该策略不得进入任何 baseline | 权限题不再被放行；新单测覆盖；fixed run false_answer=0.00 |
| P1-08 | Codex | ✅ runner guard：真实 final run 出现 vector fallback 时标 `vector_unavailable` 且不进 headline（runner.py:482/828 已接入 headline_eligible）。**小尾巴（待确认）**：现存 summary 均无该字段（guard 晚于这些 run 落地），下一次真实 final run 须确认 `vector_unavailable=false` 实际写出、且故意制造 fallback 时 headline_eligible 转 false。 | 代码已接入，待产物侧验证 |

Phase 1 即产出 Q2 第一批新 headline 数字。预算：≈400–500 次调用，约 ¥25。

风险预案：若策略变体单独消化了大部分 false_refusal，agent 的残余空间收窄——
这正是 W7 设计冻结必须论证"agent 残余场景"的原因（见 §5.1）。

------

## 4. Q2 Phase 2：Judge + CI + 红队（W4–7）

### 4.1 判官锚定验证（W4–5）— ✅ 完成，结论：不部署 judge

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| P2-01 | Codex | ✅ 锚点 = 15 条人工 census | — |
| P2-02/03 | Codex | ✅ 三候选(ragas/deepeval/custom)落地。**注**：实为同一二次家族模型(MiMo/mimo-v2.5-pro)上的 prompt adapter，**非真 RAGAS/DeepEval 库**，故非"框架 benchmark"。 | guard + 隔离 + parse fallback 单测过 |
| P2-04 | Claude | ✅ `JUDGE_AGREEMENT_REPORT.md`（含散文结论）。三候选全部 binary=0.7333(<0.80)、probe=3/5(<4/5)，全判 supported、漏 4 weak、漏 2/2 wrong_side。**deploy_judge=false**。提交 `bbf0df2`。 | 已落盘 |

**Phase 2 净结论**：无可用 judge。claim-support 维持 human-only（15 条人工 census 即证据）。
判别力下限失败的决定性项是 **wrong_side 0/2**（F4 失明）。结论是窄的——测的是该 judge
模型在此任务的判别力，**不是** "RAGAS 不行"。

### 4.2 接入与门禁（W6）

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| P2-05 | Codex | ❌ **descoped**：无 judge → 无 judge-based unsupported_claim_rate 回填。 | 不做 |
| P2-06 | Codex | ✅ **仍做且不依赖 judge**：CI 回归门禁对冻结 baseline 的 grounded/citation/retrieval 指标比对，回归即 fail。这是 eval-in-CI 治理件，judge 缺席不影响。 | 已实现：`data/eval_baselines/regression_baseline_v1.json` + `scripts/check_eval_regression.py` + CI-safe 单测；真实指标比对为手动门，不进 CI |

### 4.3 红队模块（W6 构造 ∥ W7 运行）

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| P2-07 | Claude + Owner | injection split 构造：**10 条**（瘦身版），覆盖正文指令注入、零宽/注释藏匿、诱导引用毒块、诱导绕过 ACL/deprecated 至少各 2 条 | 毒文档走 fixture 语料机制，单独 `corpus_source`；参考 OWASP LLM01 与 Promptfoo red-team 模式 |
| P2-08 | Codex | injection split 接入 runner + 指标 | injection_success_rate、gate_bypass_rate、poisoned_citation_rate |
| P2-09 | Owner | 红队 real run + 报告 | 结果如实进 EVALUATION_REPORT 新章节；失败进 taxonomy（预留 F9） |

预算：judge 验证迭代 + 全量回填 + 红队 ≈ 800 次调用，约 ¥40。

------

## 5. Q2 Phase 3：动作空间 Agent（W7–13）

### 5.1 设计冻结（W7，相当于 Q2 的 Week 0）

设计文档必须先冻结再写码，至少覆盖：

```text
1. 动作空间（类型化、白名单）：
   a. query rewrite            —— 召回弱（沿用 Q1）
   b. metadata-filtered 二次检索 —— 策略邻居挤占（攻 F1/F2 残余）
   c. version-scoped 二次检索   —— 版本混淆（原攻 F3；C2-05 后理据弱，除非新证据显示版本/相似页 top-5 崩塌，否则砍/缓）
   d. conflict-set 呈现         —— active-active
   e. 带解释拒答               —— 无可用动作
2. 诊断 schema：从 gate 结果 + 邻域构成提取失败类型，作为 controller 输入。
3. 约束（validator 强制）：动作预算 ≤2、不可绕过 ACL/state gate、全程 trace、
   LLM 提议非法动作 → 拒绝并记录。
4. agent 残余场景论证：列举 calibrated gate 仍无法处理、必须 query-dependent
   决策的场景（如版本指代不明），agent 评测围绕残余场景构造。
5. 测试床：external 校准后仍 false-refusal 的子集 + 约 10 条定向新 case + obfuscated。
6. 归因方案：逐动作（trajectory 级）记账 —— 每个动作的触发数、成功转化数、误转化数。
```

### ★ W7 期中 Scope Review（强制检查点）

| 进度状态 | 动作 |
| --- | --- |
| 正常 | 按计划全量执行 |
| 落后 ≤1 周 | 砍 D（MCP 包装，本就"看心情"）；动作空间收缩为 a + b（d/e 是终结类，保留） |
| 落后 >1 周 | 砍 LLM controller 对比（保 rule controller + pass^k）；A 降级为单控制器 |

（B 已撤——Phase 2 无可用 judge，不再有"B 移入 Q3"一说；运行时仅保留既有结构性 citation_valid。）
| 不可砍底线 | 双控制器消融（A）、逐动作归因、pass^k、红队模块存在性、headline eligibility 纪律 |

### 5.2 实现（W8–11）

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| P3-01 | Codex | 诊断提取器（gate 结果/邻域 → 失败类型） | 单测覆盖 F1/F2/F3 型诊断 |
| P3-02 | Codex | 动作 b（filtered_retrieval，c 已砍）：复用现有检索栈 + 元数据过滤器 | 过滤器只收紧、不越过 ACL（restricted 不因过滤重入）；单测 |
| P3-03 | Codex | 规则 controller（诊断 → 查表选动作） | 全分支单测 |
| P3-04 | Codex | orchestrator 集成 + trace 新字段（动作序列、预算消耗、validator 拒绝记录） | agentic loop 测试更新；停止条件不变式保留 |
| P3-05 | Codex | **LLM controller + validator（A）**：结构化输出提议动作及参数，validator 强制白名单/预算/不可绕 gate | 非法提议被拒并 trace；最坏情况退化为规则版 |
| P3-06 | Codex | 逐动作归因进 runner/metrics | 每动作独立报 trigger/success/false-recovery |
| P3-07 | — | **决议 B 已撤**（Phase 2 无可用 judge，wrong_side 0/2）：运行时不引入 LLM verifier，仅保留既有结构性 `citation_valid`。无 verifier on/off 变体。将来用更强模型 + C2-05 wrong_side 锚点重验出可用 judge 再议（Q3）。 | 不做 |
| P3-08 | Owner + Claude | 定向新 case 约 10 条（残余场景） | 走泄漏检查；gold 回填 |

### 5.3 最终对比与报告（W12–13）

| 编号 | 负责人 | 任务 | 验收标准 |
| --- | --- | --- | --- |
| P3-09 | Owner | 最终对比 run：`final_gated_calibrated` / `final_agentic_v2(rule)` / `final_agentic_v2(llm)`，各 **k=3 重复**（C 在此合并）。无 verifier 变体（B 已撤）。 | 测试床 = 残余 false-refusal 子集 + obfuscated + 定向 case（**不含** hard-negative：其残余是检索-rerank 质量问题、非 agent 动作可解，见 `Q2_AGENT_DESIGN.md §7`）；系统变体 3 个 |
| P3-10 | Codex | pass^k 与跨运行一致率指标 | pass^1 与 pass^3 并报 |
| P3-11 | Claude | trajectory 归因报告 + 可靠性报告 + 验证器 trade-off 报告 | 负结果照常三段式归档；taxonomy 扩展 trajectory 失败型（选错动作/无效动作） |
| P3-12 | Claude + Codex | README / EVALUATION_REPORT / TECHNICAL_DESIGN（新增 ADR）更新 | 叙事三句话（§0）每从句可指到 run_id |
| P3-13 | Owner | tag `v1.0-q2-agentic-eval` + release notes | Q2 收口 |

预算：对比 run（3 系统 × ~75 case × k=3 ≈ 700 次）+ B 的 judge 调用 + 调试余量
≈ 1500–2000 次调用，约 ¥80–100。

------

## 6. 求职触发器清单

以下各项不挂日期，挂事件：**开始投简历当天激活**，用当时最新真实数字制作。

```text
RESUME_BULLETS.md          —— 数字全部来自当时最新 tag 的 run
DEMO_VIDEO_SCRIPT.md       —— 3–5 分钟录屏脚本
PROJECT_REVIEW.md          —— 设计取舍复盘
INTERVIEW_QA.md 扩充       —— 基础概念题补全（v1 硬质疑题已备）
DEMO_SCRIPT.md 精修        —— Swagger 演示固定问题
OTel GenAI semconv 导出器  —— trace 薄适配层（若 Q2 期中被砍则落此处）
NIST AI RMF / OWASP 映射文档 —— 项目控制 ↔ 治理框架对照（半天）
framework mapping 一页     —— 自研 orchestrator ↔ LangGraph 概念对照（半天）
```

若 Q2 中途开始面试：用 Q1 tag 的数字 + INTERVIEW_QA v1 应战，不为面试中断 Q2 主线。

------

## 7. 预算汇总

| 项 | 估算 |
| --- | --- |
| LLM token 总成本（Q1 收尾 + Q2 全程） | ≈ ¥150–200，上限 ¥400，不构成约束 |
| 第二家族模型 API（judge 用） | 需在 W4 前备好 key；用量很小 |
| Owner 人工 | Q1 收尾 ≈ 10h；Q2 ≈ 6–8h/周（验收 + 标注 + run 审核），W12 对比 run 周 ≈ 10h |
| 日历 | Q1 收尾 2 周 + Q2 13 周 ≈ 15 周 |

------

## 8. 风险与规避

| 风险 | 表现 | 规避 |
| --- | --- | --- |
| 复标时钟被错过 | audit pass 1 拖延 → Q1 收不了尾 → 整条 judge 链推迟 | C1-01 定为收尾 D1 唯一硬 deadline |
| 校准吃掉 agent 增益面 | agent 再次零增益 | 设计冻结强制论证残余场景（§5.1.4）；零增益照常诚实归档，叙事转双控制器消融与可靠性 |
| 判官锚点 n 小 | agreement 置信区间宽 | caveat 明写 + 分歧采样扩锚路径预留 |
| LLM controller 失控 | 非法动作/预算超限 | validator 白名单硬约束，最坏退化为规则版 |
| 红队膨胀 | 10 条变 30 条 | 模块存在性优先，扩展进触发器清单 |
| Q2 范围蠕变 | 中途想加 MCP/多步规划/多 agent | 只在 W7 检查点按 §5.1 砍序决策；多 agent 维持 Q1 的 N-08 禁令 |
| run 产物丢失 | 报告引用的 run_id 不可追溯 | `data/eval_runs/` 虽 gitignore，每个被报告引用的 run 必须异地备份 summary + results |

------

## 9. 最终验收（Q2 Gate）

```text
1. final_gated_calibrated 相对 Q1 final_gated 的 trade-off 曲线落盘；
2. 判官三方 agreement 对比落盘，选定判官带人工锚定证据；
3. CI 含 eval 回归门禁；
4. injection split 实测结果落盘（成功或失败均可，必须真实）；
5. 双控制器消融（rule vs llm）落盘；
6. 逐动作归因 + pass^k 落盘；
7. judge 运行时验证器 trade-off（质量 vs 延迟/成本）落盘；
8. §0 三句话逐从句可指到 run_id；
9. tag v1.0-q2-agentic-eval。
```
