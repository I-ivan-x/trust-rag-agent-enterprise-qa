# Agent Reliability Lab 面试补课总清单（Q1-Q5）

版本：v4，按 2026-07-28 面试前封存状态更新
用途：面试前逐项补齐原理、实现、决策、证据与边界；这是一份个人学习目录，不是标准答案。
未勾选项表示 Owner 尚未确认脱稿掌握度，不代表代码或项目封存未完成，也不由自动化代替勾选。

当前事实基线：Q5=`scoped_negative_complete`；受控文本轨已关闭；开放语义价值未评估；
`v3.0-q4-reliability` 仍是稳定产品版本。当前入口见 [`docs/README.md`](README.md)。

## 使用方法

深度标记：

- **A**：必须能脱稿讲 60-120 秒，并说出项目实现、实测证据、取舍与限制。
- **B**：能准确解释机制，能定位主要代码，能回答一轮追问。
- **C**：知道概念、适用场景与本项目为何未采用即可。

每个 A 级知识点都按五句法验收：

1. 它是什么；
2. 本项目如何实现；
3. 为什么这样选；
4. 哪个实验或 artifact 支持结论；
5. 它不能证明什么，替代方案是什么。

## 0. 面试所有权与项目总图

- [ ] **A** 不看资料画出全链路：ingest -> retrieve -> rerank -> gates -> answer/agent -> validator -> sink -> grader。
- [ ] **A** 解释 Q1-Q5 各自只回答一个什么问题，以及后一阶段为何由前一阶段结果触发。
- [ ] **A** 区分项目公开定位 `Agent Reliability Lab` 与仓库历史名称 `TrustRAG`；说明为何它不再只是 RAG chatbot。
- [ ] **A** 讲清三条主线：可信回答、受治理行动、LLM 决策边界。
- [ ] **A** 讲清三平面：Control Plane、Cognitive Plane、Evaluation Plane。
- [ ] **A** 解释“LLM 是提议者，宿主代码才是授权者和执行者”。
- [ ] **A** 解释“Agent 性”来自观察环境后改变决策，而不是链长、多 Agent 或角色扮演。
- [ ] **A** 说明哪些结论是 real run、mock、synthetic、replay、offline control，不能混用。
- [ ] **A** 说明自己依靠 Codex 开发时仍承担的职责：问题定义、约束、验收、审计、取舍与最终责任。
- [ ] **A** 能现场定位并解释 8 个核心模块：`orchestrator.py`、`evidence_gate.py`、`agent/loop.py`、`govern/validator.py`、`q5_loop.py`、`q5_context.py`、`q5_runner.py`、`q5_provenance.py`。
- [ ] **B** 能从一个 case 反向追踪 task、context、policy event、tool event、terminal proposal、transition、result、grade。
- [ ] **B** 能说明哪些代码自己必须逐行读懂，哪些库级实现只需理解接口与约束。

## 1. AI 与 LLM 基础

- [ ] **A** Transformer、token、embedding、attention、上下文窗口的基本直觉。
- [ ] **A** 训练知识、上下文知识、检索证据三者的区别。
- [ ] **A** 概率生成为何带来幻觉、抖动与不可重复性。
- [ ] **A** temperature、top-p、seed 的作用；为什么 controller/judge 使用 temperature=0 仍不等于数学确定性。
- [ ] **A** system/user/tool message 的信任边界与指令优先级。
- [ ] **A** structured output、JSON mode、tool calling/function calling 的区别与失败方式。
- [ ] **A** schema validation 为什么必须由宿主执行，而不能相信模型“看起来像 JSON”。
- [ ] **A** prompt injection、indirect prompt injection、tool-output injection 的攻击面。
- [ ] **A** 为什么不要求或保存 chain-of-thought；结构化 decision basis 与 CoT 的区别。
- [ ] **A** LLM fallback、rule fallback、safe escalation 的语义区别和风险。
- [ ] **B** OpenAI-compatible API：messages、timeout、retry、usage、finish reason、JSON output。
- [ ] **B** thinking mode 与 temperature 的交互；Q5 real run 为什么显式关闭 thinking。
- [ ] **B** prompt token、completion token、cache hit/miss、调用成本与延迟分解。
- [ ] **B** 模型身份、provider、endpoint、model family 与 deployment fingerprint 的区别。
- [ ] **C** SFT、RLHF/RLAIF、DPO、蒸馏、量化、推理优化分别解决什么问题；本项目未做什么。

## 2. RAG 与信息检索基础

- [ ] **A** RAG 的基本链路、收益、失败面，以及什么时候根本不需要 RAG。
- [ ] **A** 稀疏检索与 BM25：TF、IDF、文档长度归一、`k1/b` 直觉。
- [ ] **A** 稠密检索与 bi-encoder：向量相似度、语义召回、领域偏移与信息压缩损失。
- [ ] **A** cross-encoder reranker 与 bi-encoder 的区别；为何两阶段检索常见。
- [ ] **A** RRF 的公式、rank-based 融合优点、为何不直接相加异构分数。
- [ ] **A** chunk size、overlap、section-aware chunking 对召回与上下文完整性的影响。
- [ ] **A** hit@k、recall@k、MRR、nDCG 的定义、适用场景与盲区。
- [ ] **A** “检索到 Gold”与“答案 grounded”为什么不是同一件事。
- [ ] **A** hard negative、sibling document confusion、版本/状态混淆的区别。
- [ ] **A** 参数化记忆污染为何会让“答对率”虚高；grounded-only scoring 如何约束。
- [ ] **B** HNSW 的近似最近邻直觉、召回/速度/内存权衡。
- [ ] **B** Qdrant collection、payload filtering、向量索引与 metadata 过滤。
- [ ] **B** Whoosh/BM25、本地向量库、索引重建与指纹。
- [ ] **B** BGE embedding 与 BGE reranker 的职责、CPU 部署代价与选型依据。
- [ ] **B** context budget、top-k、去重、截断与 evidence dilution。
- [ ] **B** query rewrite 何时有效、何时改变意图、如何限制新实体注入。
- [ ] **C** learned fusion、ColBERT、late interaction、HyDE、multi-query retrieval 的适用条件。

## 3. Q1：可信回答与反自欺评测

### 3.1 实现链路

- [ ] **A** Q1 承重问题：能否构建本地、可运行、可追踪、可评测的可信企业文档问答系统。
- [ ] **A** Markdown/TXT loader、YAML front matter、metadata overlay、稳定 path/ID 的实现目的。
- [ ] **A** section-aware parser/chunker 如何保留 section path、line range 与 provenance。
- [ ] **A** `bge-small-en-v1.5 + Qdrant + BM25 + RRF + bge-reranker-base` 各层职责。
- [ ] **A** context assembler 如何只把合规证据送入模型，并保留 citation metadata。
- [ ] **A** GeneratedClaim 的 `supporting_chunk_ids` 与 citation binder 的宿主侧约束。
- [ ] **A** document-state、ACL、conflict、evidence 四类 gate 的顺序和职责。
- [ ] **A** response modes 与优先级：permission、conflict、deprecated、answer/no-evidence。
- [ ] **A** 最多一次 query rewrite + second retrieval，为何是 bounded recovery 而非自由循环。
- [ ] **B** mock embedding/reranker/LLM 的用途与 headline 禁区。
- [ ] **B** 为什么 Qdrant 或真实模型不可用时不能静默降级为 mock。

### 3.2 关键决策

- [ ] **A** 为什么选择 fail-closed；错误回答与错误拒答的成本不对称。
- [ ] **A** 为什么 headline 使用 `grounded_correctness`，而不是普通 answer accuracy。
- [ ] **A** citation structural validity、citation correctness、claim support 三者区别。
- [ ] **A** 为什么 `expected_rewrite` 只能作诊断，不能进入打分。
- [ ] **A** 为什么 synthetic fixture 只能做功能回归，不能作为能力证据。
- [ ] **A** 为什么 public corpus、hard-negative corpus、eval author 要隔离。
- [ ] **A** 双向边界教训：信息过多造成泄漏，信息太少造成不可检索。
- [ ] **B** active-active conflict 为什么只做 minimal detector；为何不扩大成通用事实冲突系统。
- [ ] **B** 为什么先做可追溯与失败分析，再加更多 Agent 功能。

### 3.3 结果与攻防

- [ ] **A** 解释 Q1 的 `false_answer=0`、`citation_valid=1.00`、`grounded=0.24`、`false_refusal=0.46`。
- [ ] **A** 回答“0.24 太低是否说明失败”：区分安全地板、能力上限与拒答代价。
- [ ] **A** 回答“citation 1.00 是否等于引用语义 100% 正确”。
- [ ] **A** 解释 raw correctness 与 grounded correctness 的污染差距。
- [ ] **A** 熟悉 F1-F9：过拒、policy gate 主导、hard-negative confusion、citation support、不触发恢复、参数记忆、冲突压制、Gold 风险、injection compliance。
- [ ] **B** 能说明 Q1 哪些问题属于 retrieval、generation、policy、eval，而不是笼统归因给 LLM。

## 4. Q2：受约束恢复 Agent 与“无增益”结论

### 4.1 Agent 基础与实现

- [ ] **A** workflow、tool-using agent、autonomous agent 的区别；本项目处在哪一类。
- [ ] **A** ReAct 的 Observe-Think-Act 逻辑，以及本项目为何采用 bounded loop。
- [ ] **A** DiagnosisReport 如何由 gate 信号和检索统计确定性派生。
- [ ] **A** 类型化动作：rewrite、filtered retrieval、present conflict、refuse。
- [ ] **A** legal-action set 与多合法动作为何是 rule-vs-LLM 消融成立的前提。
- [ ] **A** RuleController 与 LLMController 在相同动作空间、工具和 validator 下的公平对比。
- [ ] **A** validator V1-V7：动作合法、预算、权限、filter 只收紧、实体约束、重新过 gate、拒绝记录。
- [ ] **A** 轨迹停止条件、最多两次非终结动作、同动作不重复与必然终止。
- [ ] **A** 检索动作后为什么必须重新执行 state/ACL/evidence gates。
- [ ] **B** proposal、validation、execution、terminal result 的数据结构与分层。
- [ ] **B** validator reject 后退化到 rule 的安全含义与评测含义。

### 4.2 决策与实验

- [ ] **A** 为什么先校准 Q1 over-refusal，再测 Agent；否则 Agent 会替错误 gate 擦屁股。
- [ ] **A** 动作 `version_scoped_retrieval` 为什么被砍：没有对应的真实残余失败面。
- [ ] **A** 为什么不用无界反思、多 Agent、跨请求记忆。
- [ ] **A** 为什么 LLM judge 候选全部未过选择门后仍然不部署 judge。
- [ ] **A** LLM-as-judge 的 self-preference、position、verbosity、wrong-side 风险。
- [ ] **A** trajectory attribution：trigger/accept/success/false-recovery 与 TF1-TF4。
- [ ] **A** pass^1、pass^3、trajectory consistency 如何衡量随机 Agent 可靠性。
- [ ] **A** 为什么 rule==LLM 是有效结论，不应通过换提示词强行制造差异。
- [ ] **B** 多动作共现稀缺为何使原消融统计能力不足。

### 4.3 结果与转向

- [ ] **A** 解释 gated `0.2273`、agentic `0.2727`、rule==LLM，为什么不足以证明 Agent 增益。
- [ ] **A** 回答“既然没增益，为什么还叫 Agent”：区分机制成立与价值主张成立。
- [ ] **A** 说明 Q2 如何证明“闭合、低熵动作映射更适合规则”。
- [ ] **A** 解释为何 Q2 结果推动 Q3 从“恢复检索”转向“治理有副作用动作”。

## 5. Q3：动作治理 Agent

### 5.1 动作与风险模型

- [ ] **A** Q3 承重问题：如何把 answer-level trust 提升到 side-effect action governance。
- [ ] **A** 四动作语义：`flag_stale`、`open_remediation_ticket`、`send_alert`、`escalate_to_human`。
- [ ] **A** `no_op` 与 `escalate_to_human` 的本质区别。
- [ ] **A** low-risk auto、high-risk approval、terminal escalation 的风险分级。
- [ ] **A** proposal、pending approval、committed、rejected/dropped 的状态机。
- [ ] **A** proposed 指标与 committed 副作用为何分开记账。
- [ ] **A** LLM 为什么不能输出或覆盖 risk tier。
- [ ] **A** evidence、ACL、requested capability 与 action legality 如何共同授权。
- [ ] **A** idempotency/dedup key、可回滚本地 sink 与审计记录。
- [ ] **B** Local MCP server 在这里解决什么；为何不用外部 Jira/Slack 写操作。
- [ ] **B** MCP tool、host validator、sink 三者边界。

### 5.2 治理运行时

- [ ] **A** Read -> Detect -> Act -> Govern -> Execute/Review 全流程。
- [ ] **A** condition detector 与 action selector 分离的意义。
- [ ] **A** rule/LLM 双控制器为何共用同一 validator。
- [ ] **A** illegal proposal 为什么必须拒绝并安全升级，绝不执行副作用。
- [ ] **A** 高风险动作为何人审前不能落 sink。
- [ ] **A** K8s public corpus + seeded metadata/policy overlay 的真实性边界。
- [ ] **A** 真实锚点场景与 synthetic overlay 场景如何分别披露。
- [ ] **B** annotations/tickets/alerts/escalations JSONL sink 的接口与替换性。

### 5.3 评测与结果

- [ ] **A** action precision、false action、unauthorized blocked、insufficient escalation、over-escalation 的定义。
- [ ] **A** anti-gaming triad 为什么必须联报：安全、有用、不偷懒。
- [ ] **A** 为什么 escalate-everything 可以刷安全指标，却不是好 Agent。
- [ ] **A** 解释 Q3 `unauthorized_blocked=1.00`、F11/F13=0、triad=False。
- [ ] **A** F10-F13：选错动作、无证据副作用、过度升级、漏升级/越权执行。
- [ ] **A** 回答“安全但选择平庸有什么价值”：安全机制已证实，能力主张未通过。
- [ ] **A** 说明 Q3 负结果如何定位到 `flag_stale` 死路与升级滥用，并触发 Q4。

## 6. Q4：可靠性校准与负转正

- [ ] **A** Q4 承重问题：能否修真实缺陷，并在冻结门槛和 held-out test 上翻正。
- [ ] **A** zero-token diagnostic 如何区分 detection miss 与 routing error。
- [ ] **A** `flag_stale` 死路径、过度升级、漏升级的根因与修复方向。
- [ ] **A** 为什么优先修规则检测/路由，而不是继续调 LLM prompt。
- [ ] **A** dev/test 物理隔离、预注册、阈值冻结、一次性终评的作用。
- [ ] **A** 为什么不能看 test 后继续调参；post-hoc 修订应如何标记。
- [ ] **A** 为什么 validator 保持不变是“能力提升未牺牲安全”的关键证据。
- [ ] **A** precision@authorized `0.4545 -> 0.6471` 的含义。
- [ ] **A** over-escalation `0.2857 -> 0.05`、triad `False -> True` 的含义。
- [ ] **A** unauthorized blocked 1.00、F11/F13=0 为什么必须与 usefulness 同时报告。
- [ ] **A** 小样本“真但薄”怎么表达：效应可核验，不等于广泛泛化。
- [ ] **A** 为什么不降低 `0.60/0.30` 门槛来获得漂亮结果。
- [ ] **A** 规则优于/等于 LLM 时，为什么生产架构应保留确定性 controller。
- [ ] **B** OpenInference span kinds 与 OTel GenAI attributes 如何映射 pipeline。
- [ ] **B** run manifest 应包含模型、prompt、index/corpus、seed、commit、成本与门槛。
- [ ] **B** CI release gates 如何阻止 mock、leakage、安全回归与 triad 失败冒充 headline。
- [ ] **B** 区分 tracing、logging、metrics、artifact provenance。

## 7. Q5：Selective Hybrid Agent 架构

### 7.1 核心命题与任务分层

- [ ] **A** Q5 原始问题：什么任务需要 LLM，什么任务不需要，如何只在有价值时调用。
- [ ] **A** deterministic、semantic frontier、adversarial/high-risk 三类任务的定义。
- [ ] **A** 为什么 `stratum` 只能属于 grader metadata，runtime 不可读取。
- [ ] **A** rule-only、LLM-only、hybrid、escalate-everything 四种对照的作用。
- [ ] **A** 为什么 rule baseline 必须拥有相同工具、状态、validator 与 outcome grader。
- [ ] **A** ex-ante router、offline oracle 与 label-aware cheating 的区别。
- [ ] **A** selective routing 的目标不是省 token 本身，而是降低无价值概率调用和方差。

### 7.2 DecisionContext 与信任边界

- [ ] **A** LLM 可见的 authorized evidence、actor claims、capability、trusted observations、legal actions、budget。
- [ ] **A** LLM 不可见的 blocked text、Gold、stratum、required observation、内部 control fields。
- [ ] **A** blocked evidence 为何只暴露 count/opaque id/reason category。
- [ ] **A** role、requested capability、action policy 的交集授权。
- [ ] **A** terminal proposal 为什么必须重新授权，防止 TOCTOU 与初始授权扩张。
- [ ] **A** `investigate` capability 为什么不能继承 side-effect 权限。
- [ ] **A** authorized evidence citation 与 trusted observation request lineage 的作用。
- [ ] **B** `extra=forbid`、frozen Pydantic models、enum、pattern、required fields 的安全意义。

### 7.3 Observation loop 与工具合同

- [ ] **A** 三类 read-only tools：policy exception、change state、incident impact。
- [ ] **A** 最多 2 observations、最多 1 terminal proposal、总 step <=3 的终止证明。
- [ ] **A** observation planning、state update、terminal-only replan 的完整状态机。
- [ ] **A** required observation recall 与 attempted/completed recall 的区别。
- [ ] **A** duplicate successful observation 为什么是 Agent-loop 缺陷。
- [ ] **A** timeout 为什么不等于成功 observation，也不应污染 completed key。
- [ ] **A** timeout 可在原预算内重新规划，schema-invalid 为什么应立即 fail-closed。
- [ ] **A** unresolved-state side-effect guard 为何禁止过早终结。
- [ ] **A** tool args 必须来自 grounded allowed values，不能新增实体或使用别名猜测。
- [ ] **A** Pydantic args model 作为 JSON Schema 单一来源的意义。
- [ ] **B** schema compaction 为何可删 title/default/description，却不能删 enum/pattern/required/additionalProperties。
- [ ] **B** observation result 中 trusted structured state 与 untrusted text 的隔离。

### 7.4 Semantic binding 与执行

- [ ] **A** v3 的 reason/action contradiction：模型“说对理由却选错动作”为何发生。
- [ ] **A** `Q5PolicyDisposition` 作为 typed semantic IR 的作用。
- [ ] **A** 模型选择 disposition、宿主编译 action、validator 执法的职责分解。
- [ ] **A** 为什么禁止模型同时输出 disposition 与独立 action，避免多份真相。
- [ ] **A** disposition -> action 双射映射的收益与局限。
- [ ] **A** evidence chunk + observation request 共同构成 decision basis。
- [ ] **A** policy block 与普通 human review 的 provenance 区别。
- [ ] **A** safe fallback 为什么不能伪造 decision basis 或冒充成功决策。
- [ ] **B** fallback closed taxonomy、唯一 causal witness、跨 trial witness 移植为何必须被拒绝。

## 8. Q5：评测协议、真实运行与迭代过程

### 8.1 数据与 outcome grading

- [ ] **A** `tasks/environment/runtime_cases/gold` 物理分离，各自由谁读取。
- [ ] **A** runner API 为什么完全不接受 Gold object。
- [ ] **A** final action 正确、final environment state 正确、trajectory-qualified success 的区别。
- [ ] **A** counterfactual pairs：policy fixed/state changed 与 state fixed/policy changed。
- [ ] **A** within-pair/cross-pair success 如何检验状态适应与策略解释。
- [ ] **A** F14-F18：错路由、观察/适应失败、outcome mismatch、泄漏、policy binding failure。
- [ ] **B** 36 cases x 3 systems x k=3 = 324 trial matrix 如何校验缺失、重复和额外行。

### 8.2 Gate 与统计

- [ ] **A** G0 safety floor、G1 LLM value、G2 non-inferiority、G3 efficiency、G4 cross-family、G5 anti-gaming。
- [ ] **A** 为什么 G1 同时要求 effect size >=0.10 和 paired-bootstrap CI lower >0。
- [ ] **A** non-inferiority 与“完全相等”的区别；margin 为什么必须预注册。
- [ ] **A** call ratio、token ratio、call avoidance 的分母与解释。
- [ ] **A** pass^1/pass^3 与按 case/run 配对 bootstrap 的关系。
- [ ] **A** G4 未运行必须是 false/not evaluated，不能写成 pass。
- [ ] **A** preflight 为什么要在真实请求前检查 claim headroom，而不仅检查代码能跑。

### 8.3 Protocol 与 artifact integrity

- [ ] **A** raw artifacts 与 graded artifacts 为什么分开；grader 如何离线连接 Gold。
- [ ] **A** manifest、hashes、summary、gates、report 的角色和相互重算关系。
- [ ] **A** canonical JSON、SHA-256、source inventory、Git commit/blob provenance 的意义。
- [ ] **A** protocol v1-v4 冻结分派，为什么不能用新 verifier 悄悄改写旧语义。
- [ ] **A** replay 与 rerun 的区别；为什么 verifier 修复后不应重跑模型来覆盖证据。
- [ ] **A** mutation testing 如何验证 verifier 真能 fail closed，而不只是 happy-path 通过。
- [ ] **A** lineage closure：proposal、trajectory、terminal event、transition、sink、result 必须一致。
- [ ] **A** fallback causal lineage、policy-block attestation、source hash inventory 防什么攻击。
- [ ] **B** trusted real client、provider identity、TLS-only readiness 与 zero-request preflight。
- [ ] **B** cost basis：provider billed、provider tokens estimated、local estimate、unavailable 的区别。
- [ ] **B** empty-set metric 为什么应是 `null/vacuous=true`，不能伪造成 1.0。

### 8.4 每轮失败如何推动下一轮

- [ ] **A** v1 real：tool schema invalid、required observation recall=0；为什么先修协议而不是调模型。
- [ ] **A** v2 real：观察闭环改善，但固定状态表 solvability=1.00；为什么判定 baseline 太弱。
- [ ] **A** v3 real：recall/安全/效率成立，semantic binding 失败；为什么 G1 仍失败。
- [ ] **A** v4 semantic IR：为什么修复 action/reason 脱节后仍不能直接声称 LLM 必要。
- [ ] **A** step-level cognitive routing：规则负责 observation planning，LLM 只做 terminal binding。
- [ ] **A** value ledger 的 beneficial/neutral/harmful、oracle regret、incremental success/100 calls。
- [ ] **A** 108 neutral、0 beneficial、42 Hybrid calls、0 incremental success 对 claim 的含义。
- [ ] **A** strong symbolic baseline 为什么是必须主动加入的“最强反方”。
- [ ] **A** `claim_headroom` 与 `beneficial_evidence_absent` blocker 各代表什么。

## 9. Q5 Boundary A-F 与最终结论

- [ ] **A** 有限数据集总能被查表硬编码；“数学上只有 LLM 能解”为什么不是可辩护命题。
- [ ] **A** practical deterministic frontier 与 general natural-language capability 的区别。
- [ ] **A** Boundary A：closed vocabulary grammar 应由 parser/compiler 执行，LLM abstain。
- [ ] **A** Boundary B：controlled prose 20/20 被通用 parser + antecedent resolver 解决。
- [ ] **A** Boundary C：post-hoc compositional challenger 解决先前 16/16 abstentions。
- [ ] **A** Boundary D：family + token/state shortcut 16/16，揭示 label shortcut。
- [ ] **A** Boundary E：runtime-only parser 对 covered/uncovered 均 32/32，撤销旧 readiness。
- [ ] **A** Boundary F：独立 post-hoc challenger 对新 uncovered 30/32，coverage .9375、risk 0，仅余 2 abstentions。
- [ ] **A** preregistered parser 与 post-hoc challenger 为什么必须分开报告。
- [ ] **A** coverage、conditional accuracy、conditional risk、abstention 的定义与联合解读。
- [ ] **A** renderer family、policy family、semantic phenomenon、action balance 如何抵抗捷径。
- [ ] **A** family-only、phenomenon-only、template-only、majority、lexical、pair-neighbor attacks。
- [ ] **A** metamorphic/invariance tests：改资源名、顺序、无关句后行为应保持什么。
- [ ] **A** Policy IR oracle 的作用、为何只能用于 offline grading。
- [ ] **A** Boundary 形成后为什么停止 K1、DeepSeek/Xiaomi 与 q5_test，而不是继续“找赢法”。
- [ ] **A** Q5 正式结论：受控 policy prose 仍在 deterministic frontier；LLM 语义增量在当前 scope 未证明。
- [ ] **A** Q5 已证明的正向能力：选择性调用机制、观察适应、安全不变量、效率、证据完整性、强 baseline 审计。
- [ ] **A** Q5 未证明的内容：open-world semantics、生产泛化、多模型跨家族正增量、真实业务 ROI。
- [ ] **A** 为什么 scoped negative result 是高价值工程结论，而不是“Q5 白做”。
- [ ] **A** 最终架构建议：parser/compiler first -> unresolved open semantics 才调用 LLM -> unsafe/ambiguous 交人。

## 10. 评测科学与统计基础

- [ ] **A** hypothesis、baseline、treatment、outcome、confounder、ablation 的定义。
- [ ] **A** capability metric、safety metric、efficiency metric、diagnostic metric 不可混写。
- [ ] **A** micro/macro average、case-level 与 trial-level 分母。
- [ ] **A** precision、recall、false-positive/false-negative 在 answer 与 action 场景中的不同成本。
- [ ] **A** paired experiment 为什么优于不配对平均；counterfactual pairing 的价值。
- [ ] **A** bootstrap 的重采样单位、95% CI 直觉、为何小样本 CI 很宽。
- [ ] **A** effect size 与 statistical significance 为什么必须同时看。
- [ ] **A** pass@k 与 pass^k 的不同含义，避免概念混淆。
- [ ] **A** calibration、threshold sweep、多重比较与 test-set overfitting。
- [ ] **A** preregistration、held-out、one-shot、post-hoc analysis 的证据等级。
- [ ] **A** data leakage、label leakage、control-field leakage、identity shortcut 的区别。
- [ ] **A** distribution shift、external validity、construct validity、benchmark validity。
- [ ] **A** strong baseline、oracle upper bound、headroom、regret 的定义。
- [ ] **A** 为什么“LLM 胜过弱规则”不能证明 LLM 必要。
- [ ] **A** 为什么“parser 被 post-hoc 扩展”会降低原 benchmark 的含金量。
- [ ] **B** Cohen's kappa、基率问题、人工锚点与 judge agreement。
- [ ] **B** Wilson interval、bootstrap interval、n<5 不报百分比的直觉。
- [ ] **B** vacuous truth、空分母与 nullable metric 的正确建模。
- [ ] **B** latency p50/p95、cost per success、token accounting 的正确比较。

## 11. AI 安全、治理与可靠性

- [ ] **A** fail-open 与 fail-closed 的适用条件及可用性代价。
- [ ] **A** defense in depth：模型约束、schema、ACL、evidence、validator、HITL、sink。
- [ ] **A** least privilege、capability-based authorization、deny by default。
- [ ] **A** authentication、authorization、ACL、RBAC 的区别。
- [ ] **A** retrieval 后过滤与 retrieval 前过滤的泄漏/召回权衡。
- [ ] **A** prompt injection 不能只靠 prompt 防御；为何要划分 trusted/untrusted fields。
- [ ] **A** output validation 与 semantic validation 的区别。
- [ ] **A** TOCTOU、terminal reauthorization 与状态变化风险。
- [ ] **A** irreversible side effect、approval bypass、unsafe tool call 的威胁模型。
- [ ] **A** idempotency、deduplication、retry safety、timeout recovery。
- [ ] **A** human-in-the-loop 何时是治理机制，何时会退化成 all-escalate。
- [ ] **A** safety floor 与 usefulness frontier 为什么必须分别证明。
- [ ] **A** auditability、traceability、provenance、attestation 的区别。
- [ ] **B** OWASP LLM Top 10 中 prompt injection、insecure output handling、excessive agency。
- [ ] **B** NIST AI RMF 的 Govern/Map/Measure/Manage 与本项目的映射。
- [ ] **C** sandbox、secret isolation、tenant isolation、policy-as-code、OPA 的生产扩展方向。

## 12. Agent Runtime / Infra 知识

- [ ] **A** state machine、event sourcing、append-only ledger 在 Agent runtime 中的价值。
- [ ] **A** policy、planner、tool executor、validator、environment、sink 的接口边界。
- [ ] **A** control flow 与 data flow；谁能读什么、谁能写什么。
- [ ] **A** bounded loop 的终止性、预算不变量和最坏调用上界。
- [ ] **A** typed tool contract、schema evolution、backward compatibility。
- [ ] **A** deterministic router 与 learned router 的优缺点；小数据为何不适合伪精确 learned routing。
- [ ] **A** rule path、LLM path、human path 的四象限决策。
- [ ] **A** fallback、retry、replan、escalation 四种恢复动作不能混为一谈。
- [ ] **A** per-step cognitive routing 为何比 trial-level routing 更精确。
- [ ] **A** environment transition 与 outcome grader 为何比 action-string scoring 更可信。
- [ ] **B** async tool execution、queue、checkpoint、resume、dead-letter queue 的生产化方向。
- [ ] **B** distributed tracing 中 trace/span/event/link/baggage 的区别。
- [ ] **B** SLO/SLI：success、unsafe rate、p95 latency、cost、escalation backlog。
- [ ] **B** canary、shadow、offline replay、rollback 如何用于 Agent 发布。
- [ ] **C** LangGraph node/edge/state/checkpoint 与本项目自研 loop 的映射。
- [ ] **C** multi-agent、memory、long-running jobs、tenant isolation 为何不在当前证据范围。

## 13. Python、API 与工程实现

- [ ] **A** Pydantic v2：BaseModel、ConfigDict、Field、validator、serialization、JSON Schema。
- [ ] **A** `extra="forbid"`、frozen model、StrEnum 如何降低协议漂移。
- [ ] **A** dataclass、Pydantic model、Protocol 各自适用边界。
- [ ] **A** FastAPI 路由、依赖注入、lifespan、错误响应、OpenAPI。
- [ ] **A** pytest fixture、parameterize、monkeypatch/mock、unit/integration/regression。
- [ ] **A** mutation test 与普通单测的差异。
- [ ] **A** JSON、JSONL、manifest、sidecar 的选择理由。
- [ ] **A** canonical serialization 与跨平台 LF-normalized hashing。
- [ ] **A** stable ID、dedup key、content hash、source hash 的区别。
- [ ] **A** exception、timeout、parse error、model error 如何分类而非吞掉。
- [ ] **A** pure function、dependency injection、side-effect boundary 为何提高可测性。
- [ ] **B** type hint、`from __future__ import annotations`、mypy 类静态思维。
- [ ] **B** `lru_cache`/单例模型加载的收益、配置污染与测试隔离风险。
- [ ] **B** uv、pyproject、lockfile、Ruff、pytest、npm build 的交付链。
- [ ] **B** Git commit/parent/tag、clean worktree、历史 artifact byte stability。
- [ ] **B** REST API 的幂等性、状态码、审批接口与并发更新风险。
- [ ] **C** Docker/Compose、模型权重挂载、健康检查、生产配置管理。

## 14. 数据、语料与实验工程

- [ ] **A** public、synthetic fixture、seeded overlay、adversarial namespace 的边界。
- [ ] **A** corpus author 与 eval author 隔离解决什么偏差。
- [ ] **A** metadata overlay 为什么不直接篡改公共正文。
- [ ] **A** task authoring、runtime case、Gold、topology、renderer 的物理隔离。
- [ ] **A** case balance、family balance、action balance、false branch balance。
- [ ] **A** counterfactual pair 的单变量不变量如何机械验证。
- [ ] **A** unique policy text、renderer family、action phrase exposure 的捷径风险。
- [ ] **A** source inventory 为什么要封闭 parser/compiler 依赖，而不只 hash 主文件。
- [ ] **A** q5_test 从未创建/读取的意义，以及为什么不能把 dev 结果包装成 test。
- [ ] **B** public corpus license、provenance、数据声明与可复现下载。
- [ ] **B** dataset versioning、archive、sealed Gold、migration receipt。

## 15. Demo 与技术叙事

- [ ] **A** 90 秒版本：Q1 可信回答 -> Q3/Q4 受治理行动 -> Q5 决策边界。
- [ ] **A** 3 分钟版本：问题、机制、关键轨迹、数字、限制、结论。
- [ ] **A** 用一个 Authorized、一个 Insufficient、一个 Unauthorized case 演示 runtime。
- [ ] **A** 用一个 Q5 case 展示 route -> observe -> bind -> compile -> validate -> outcome。
- [ ] **A** 在页面上明确 real/mock/synthetic/offline control，避免视觉叙事夸大证据。
- [ ] **A** 解释为什么项目结论不是“LLM 没用”，而是“闭合任务先用编译器，开放语义才值得评测 LLM”。
- [ ] **A** 能把负结果讲成决策收益：停止无价值模型调用、阻止错误产品路线。
- [ ] **B** 能展示 manifest、trace、mutation rejection，而不是只展示漂亮 UI。
- [ ] **B** 能说明前端展示与真实 FastAPI runtime、冻结 artifacts 的关系。

## 16. 高频面试攻击题清单

### 项目真实性与所有权

- [ ] **A** “项目主要由 Codex 写，你本人到底做了什么？”
- [ ] **A** “随机打开一个核心文件，你能解释数据流和不变量吗？”
- [ ] **A** “不用 Codex，你能从零实现哪个最小版本？”
- [ ] **A** “哪三个决策是你否决 AI 建议后做出的？”
- [ ] **A** “你如何发现 Codex 实现或 verifier 自己有错？”

### 架构与 Agent 定义

- [ ] **A** “这到底是 Agent，还是规则工作流套了名字？”
- [ ] **A** “为什么不用 LangChain/LangGraph，为什么自研 loop？”
- [ ] **A** “为何不用 multi-agent、memory、reflection？”
- [ ] **A** “LLM 不掌握执行权，是否还算 Agent？”
- [ ] **A** “parser-first 会不会把系统做回传统专家系统？”

### RAG 与基础能力

- [ ] **A** “BM25、embedding、reranker 分别解决什么？”
- [ ] **A** “RRF 为什么合理，参数如何选？”
- [ ] **A** “grounded 0.24 为什么值得写简历？”
- [ ] **A** “citation_valid=1 是否在玩指标？”
- [ ] **A** “为什么 reranker 有时让结果更差？”

### 安全与治理

- [ ] **A** “LLM 构造合法 JSON 但语义恶意怎么办？”
- [ ] **A** “ACL 为什么不是只在检索前做一次？”
- [ ] **A** “人审队列积压时系统如何处理？”
- [ ] **A** “工具 timeout 后重试会不会重复副作用？”
- [ ] **A** “fallback 是否可能掩盖模型错误并虚增成功率？”

### 评测与统计

- [ ] **A** “为什么 36 个 dev case 足以或不足以支持你的结论？”
- [ ] **A** “为什么用 paired bootstrap，不用 t-test？”
- [ ] **A** “CI 包含 0 时你能声称什么？”
- [ ] **A** “mock k=3 通过为什么不能代表真实模型？”
- [ ] **A** “你如何证明没有 Gold leakage？”
- [ ] **A** “为什么 test 不创建反而是正确决定？”

### Q5 核心质疑

- [ ] **A** “你不是没有证明 LLM 价值吗，Q5 有什么含金量？”
- [ ] **A** “为什么不用更强模型继续跑，可能马上就赢？”
- [ ] **A** “强 parser 是看过数据后写的，还公平吗？”
- [ ] **A** “post-hoc parser 击穿 benchmark，说明 benchmark 设计失败吗？”
- [ ] **A** “30/32 仍有两条需要 LLM，为什么不运行 K1？”
- [ ] **A** “如何设计真正能检验 open-world semantic value 的下一代数据？”
- [ ] **A** “LLM 必要性与 LLM 工程经济性有什么区别？”

### 生产化与边界

- [ ] **A** “本地 JSONL sink 距生产还有多远？”
- [ ] **A** “如何做多租户、并发、持久化、灾备与审计保留？”
- [ ] **A** “如何接真实 IAM、Jira、Slack、数据库而不破坏安全边界？”
- [ ] **A** “如何定义线上 SLO、canary、rollback 与 incident response？”
- [ ] **A** “个人项目没有用户和业务 ROI，如何证明产品价值？”

## 17. 必须背熟的数字与状态

| 阶段 | 必背事实 | 面试限定语 |
| --- | --- | --- |
| Q1 | false answer `0`; citation structural validity `1.00`; grounded `0.24`; false refusal `0.46` | real evaluated result；安全强、覆盖保守 |
| Q2 | gated `0.2273`; agentic `0.2727`; rule == LLM | 仅薄弱增量，不支持 LLM controller 优越性 |
| Q3 | unauthorized blocked `1.00`; F11/F13 `0`; triad `False` | 安全成立，选择能力未达门 |
| Q4 | precision authorized `0.4545 -> 0.6471`; over-escalation `0.2857 -> 0.05`; triad `False -> True` | held-out、阈值冻结、validator 不动；结果真但样本薄 |
| Q5 v3 real | observation recall `1.00`; Hybrid call/token ratio `.590909/.644393`; semantic uplift `.083333`; CI `[-.25,.416667]` | G0/G2/G3/G5 pass，G1 fail，G4 not run |
| Q5 v4 value | `108 neutral / 0 beneficial`; Hybrid `42 calls / 0 incremental successes`; symbolic `1/1/1` | deterministic mock + offline controls，不是 real LLM 胜负 |
| Boundary F | post-hoc `30/32`; coverage `.9375`; conditional accuracy `1`; risk `0`; abstain `2` | controlled handwritten prose 仍在 practical deterministic frontier |
| 当前 Q5 | K1 false；q5_test absent；Xiaomi/confirmatory `0` | scoped negative complete；不声称 open-world LLM 无价值 |

## 18. 建议学习顺序

### 第一轮：先保住项目所有权

- [ ] 先学第 0、3-9、17 节；能完整讲 Q1-Q5 因果链。
- [ ] 每个 Q 准备“问题、实现、决策、结果、限制”五张口述卡。
- [ ] 逐行读懂 8 个核心模块，并手画一个合法轨迹和一个被拒轨迹。

### 第二轮：补齐面试基础

- [ ] 学第 1、2、10、11 节 A 级内容。
- [ ] 手算一次 BM25/RRF 小例子、一次 precision/recall、一次 call ratio。
- [ ] 用 10 个 trial 的玩具数据手推一次 paired outcome 与 bootstrap 直觉。

### 第三轮：补 Agent Infra 与工程

- [ ] 学第 12-14 节 A/B 内容。
- [ ] 能解释 schema、state machine、hash closure、mutation test、OTel trace。
- [ ] 本地重跑一组 unit test、一组 release gate、一次 mock trajectory。

### 第四轮：模拟攻防

- [ ] 第 16 节每题准备 30 秒、90 秒两个版本。
- [ ] 让提问者随机选文件、数字、失败 case，不按准备顺序回答。
- [ ] 任何回答都主动给限定语，绝不把 mock、dev、offline control 说成 held-out real evidence。

## 最终验收标准

达到以下条件，才算真正“拥有”这个 Codex 驱动的项目：

- [ ] 能不看文档画架构、讲 Q1-Q5，并复述关键数字与证据等级。
- [ ] 能解释至少一个设计替代方案，以及为何项目没有选它。
- [ ] 能追踪一个 case 的完整数据与控制流，并指出三个 fail-closed 点。
- [ ] 能解释 Q5 为什么停止，以及停止为项目和业务节省了什么错误投入。
- [ ] 能坦诚说明 Codex 的贡献，同时用可复现验收、代码理解和独立判断证明自己的工程所有权。
