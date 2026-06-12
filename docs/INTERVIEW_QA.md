# Interview QA（v2）

> 第一部分：硬质疑题（负结果应对）。第二部分：基础概念题（每题答案锚定本项目实现）。
> 原则：不美化、不隐藏；每个负结果按"现象 → 根因（带证据）→ 下一步"三段式回答；
> 所有数字必须能对应到 Week 6 real run 的 run_id。
> 配套补课清单：`docs/STUDY_CHECKLIST.md`。

------

## 数字速查表（必须背熟，面试中先于面试官说出口）

全部来自 Week 6 真实评测（DeepSeek real run / 真实 embedding + reranker）：

| 数字 | 含义 | 来源 run |
| --- | --- | --- |
| grounded_correctness 0.24 | final 系统 external headline | `week6-real-external-full` |
| false_answer_rate 0.00 | 零错误回答 | 同上 |
| refusal_rate 0.74 / false_refusal_rate 0.46 | 过度拒答的真实代价 | 同上 |
| citation_valid 1.00 | **结构**有效率，非人工 support | 同上 |
| direct_llm raw 0.20 / grounded 0.00 | 污染信号实测 | 同上 |
| doc_hit@5：vector 0.60 / bm25 0.80 / hybrid 0.80 / +rerank 0.78 | 检索消融 | `week6-external-retrieval-ablation` |
| hard_negative_error_rate 1.00 / doc_hit@5 0.05 | 压力测试全灭 | `week6-hard-negative-*` |
| obfuscated：gated 0.3333 = agentic 0.3333 | agentic 零增益 | `week6-real-obfuscated-full` |

------

## Q1（核心质疑）：grounded 只有 0.24，agentic 没提升，hard negative 全败——这个项目有什么价值？

**危险回答（不要说）：**
- "数据集太难了 / 时间不够，调一调就能上去"（甩锅 + 空头支票）；
- "虽然 0.24，但 raw correctness 有 0.24，模型其实答对很多"（混淆指标，当场暴露不懂自己的评测体系）；
- 直接跳过数字谈架构（被认定在回避）。

**推荐回答（约 90 秒）：**

> 这三个数字都是真实的，我先说清楚 0.24 是什么：grounded_correctness，要求答案正确、
> 引用来自检索上下文、且引用支持核心 claim，三者同时成立才得分。
>
> 拆开看，瓶颈不是答错，是不答：同一次 run 里 false_answer_rate 是 0，
> refusal_rate 是 0.74，其中 false_refusal 0.46。也就是说系统按 fail-closed
> 设计运行——权限、过期、冲突、证据不足四道 gate 全部宁拒勿错。0.24 不是质量上限，
> 是"安全姿态在校准之前的已度量代价"，失败分析里 F1/F2 给了根因：检索邻域里出现
> restricted/deprecated 邻居就会触发门控。
>
> 这个项目交付的价值有三层。第一，一个零错误回答、全链路 trace 可审计的可信问答骨架——
> 企业场景里 false answer 的成本远高于 false refusal，这个不对称是设计前提。
> 第二，一套防自欺的评测体系：grounded scoring 隔离训练数据污染（direct_llm 裸答
> raw 0.20 但 grounded 0，说明模型背过语料但给不出合法引用）、泄漏检查、
> headline eligibility 用测试锁死哪些数字允许引用。第三，正是这套体系如实测出了
> 您说的三个问题，并且每个都有 trace 级根因和排序过的修复路线——
> 下一步是 evidence gate 阈值扫描，把 false refusal 从 0.46 往下压。
>
> 如果我汇报的是一个 80 分但说不清哪 20 分是错的系统，那才是没有价值。

**可能追问：**
- "那你预计校准后能到多少？" → 不给承诺数字："我只引用跑出来的数字。能给的是机制判断：
  0.46 的 false refusal 里有相当比例是 F2 类'邻居触发'，这类靠策略区分'存在 deprecated
  邻居'和'只有 deprecated 证据'就能转化，不需要放松 grounding 约束。"
- "0.74 拒答率的系统能上线吗？" → 见 Q7。

------

## Q2：agentic loop 零增益，为什么还好意思叫 RAG-Agent？

**危险回答：**"其实有一点提升只是没测出来" / "加几轮重写就会好"（无证据 + 违背自己的停止条件设计）。

**推荐回答：**

> 项目名里的 Agent 由一个受控 recovery loop 支撑：只在 evidence gate 判定不足时触发、
> 最多重写一次、二次检索一轮、有停止条件、写 trace、并且不允许绕过 ACL 和 state gate——
> 权限不足的 query 按设计禁止 rewrite。我专门为它构造了 obfuscated split（15 条缩写/
> 口语化变体，gold 与原 case 相同，只比终态），这是它的专属受控实验。
>
> 实验结果是打平：0.3333 对 0.3333，整个 run 只发生一次 rewrite 调用且未被接受。
> 我能解释为什么：当前 74% 的拒答大部分走 permission/deprecated/conflict 路径，
> 这些路径按设计不允许 rewrite，所以 rewrite 几乎没有触发面。这是失败分析里的 F5。
>
> 所以我的结论是顺序问题：先做 gate calibration 把流量从策略路径释放到
> evidence-insufficient 路径，agentic 才有发挥空间，在那之前继续优化 rewrite
> 是在错误的瓶颈上使劲。我认为"实现了受控 agent、用实验证伪了它当前的收益、
> 并能定位约束条件"，比一个无法复现的'提升了 X%'更有工程含金量。

**追问防御：**"为什么不让 rewrite 多跑几轮试试？" → "停止条件是设计承诺：无限重写
意味着不可控的延迟、成本和绕过门控的风险。改的应该是触发面（gate 校准），不是放开循环上限。"

------

## Q3：hard negative 全军覆没（error rate 1.0），是不是系统根本不行？

**推荐回答：**

> 这个 split 的定位就是压力测试：30 对相邻版本/相似标题文档，专门构造来打检索。
> 结果 doc_hit@5 只有 0.05，error rate 1.0，确实是全灭，报告里原文写的是
> "serious failure mode"，没有包装成鲁棒性。
>
> 归因上我保留了两个假设，因为现有证据不足以完全区分：F3，检索/rerank 真的无法分辨
> 相似文档——trace 显示 0001/0002 的 gold 被 0019/0020 组的全局相似文档挤占；
> F8，gold 设计本身可能有缺陷——query 用"side A/B"指代目标，但索引没有把
> pair/side 元数据暴露给检索，这个信息语义检索从自然语言里推不出来。
> 承认"评测设计也可能有问题"写在失败分析里，这是有意的：评测体系本身也要可质疑。
>
> 下一步排了序：先人工裁定 5–10 对，区分 F3 和 F8 的占比；F3 的部分上
> metadata-aware / version-aware rerank；F8 的部分修 gold 定义。

**这一题的隐藏得分点**：敢于质疑自己的评测集（F8），面试官会默认你做过真实评测工作。

------

## Q4：rerank 加了反而更差（0.78 < 0.80），reranker 白做了？

**推荐回答：**

> 消融结果是 hybrid_rrf_rerank 在 hit@5 / doc_hit@5 / recall / MRR 上全面略低于
> hybrid_rrf，所以报告里明确写了 "No rerank improvement may be claimed"，
> 所有材料里都不声称 rerank 提升——这是消融纪律：只声称测到的东西。
>
> 为什么会这样，我有假设但没下结论：bge-reranker-base 是通用域 cross-encoder，
> 语料是 FastAPI 文档子集只有 442 chunks，而且 external query 一半来自真实人类提问、
> 关键词信号强，BM25 本身就到了 0.80。rerank 不是免费午餐，需要按域验证——
> 这正是这次消融的价值：它阻止了我把'加了 reranker'当成'检索变好了'写进简历。
>
> 这次消融里干净的正向结论只有一个：hybrid 相对 vector-only 把 doc_hit@5 从
> 0.60 提到 0.80。我只讲这一个。

------

## Q5：citation_valid 是 1.00，你的引用真的 100% 准确？

**危险回答**：直接说"是"。这是埋给你的坑。

**推荐回答：**

> 不是。citation_valid=1.0 是**结构**有效率：每条 citation 的 chunk_id 都来自
> 检索上下文（ContextPack），LLM 编造的 chunk_id 会被 citation binder 拦截。
> 它不等于人工判定的 claim support——hard negative run 里 citation_valid 同样是 1.0，
> 但 grounded_correctness 是 0：引用结构合法，引到的却是错误一侧的证据，
> 这就是失败分类里的 F4。
>
> 所以人工 citation-support audit 是 Q1 收尾的硬性 blocker：协议已冻结
> （40 条 claim 理想 / 25 条最低，三档判定 supported/weak/unsupported，
> 加 wrong_side 标记，一周后盲复标算自一致率），在它完成之前我不会说
> "citation accuracy X%"。

------

## Q6：为什么不把拒答阈值调低？覆盖率上去，数字立刻好看。

**推荐回答：**

> 因为那是在优化报表，不是优化系统。企业文档场景里 false answer 和 false refusal
> 的成本不对称：拒答一个能答的问题，用户去翻文档；自信地答错一个权限、合规或版本问题，
> 是事故。所以 Q1 的默认姿态是 fail-closed，先把 false answer 压到 0，
> 再用数据做校准——而不是反过来。
>
> 调阈值本身就是计划内的下一步，但形式是 threshold sweep 画出
> false_refusal vs false_answer 的 trade-off 曲线，让每个工作点的代价可见，
> 而不是挑一个让 headline 最好看的点。曲线本身是交付物，单点不是。

------

## Q7：这个项目和跑一遍 LangChain 教程的 RAG 项目有什么区别？

**推荐回答（清单式，挑 3–4 个讲）：**

> pipeline 本身没有区别，谁都能搭。区别在围绕它的治理：
>
> 1. headline 只认 grounded_correctness——答对但引用不支持不得分，
>    参数化记忆作弊被指标设计排除，并且有实测证据（direct_llm raw 0.20 / grounded 0）；
> 2. 评测防自欺：语料作者与出题作者隔离、标题泄漏与答案句抄写自动检查、
>    external query 一半来自真实人类提问、ACL/状态元数据用可复现 overlay 叠加在真实公开文本上；
> 3. 哪些数字允许引用是代码合约：summary 里有 headline_eligible / mock_used 字段，
>    有单元测试守着，mock 数字想进报告会挂测试；
> 4. 有失败分类：F1–F8 每条带 trace 证据、根因假设和修复优先级。
>
> 最直接的验证方式：教程项目的评测结果都很漂亮，我的不漂亮——
> agentic 打平、rerank 不增益、hard negative 全灭都在报告里。
> 伪造漂亮数字容易，伪造诚实的失败没有动机。负结果是这个项目真实性的水印。

------

------

# 第二部分：基础概念题（答案锚定本项目）

回答策略：概念一句话 + 本项目怎么做的 + （如有）实测数字。永远落回项目。

## 检索层

**B1 为什么用 section-aware chunking 而不是固定窗口切分？**

> 企业文档的语义边界就是标题结构：一个 SOP 的步骤、一个 API 的参数说明天然成段。
> 固定窗口会把"v1 的限制"和"v2 的限制"切进同一个 chunk，引用就指不清了。
> 我按 H1/H2/H3 切分并保留 section_path 和行号区间，每个 chunk 携带完整元数据
> （status/access/version/corpus_source），这是后面 citation 能精确到 chunk、
> gate 能按 chunk 过滤的前提。长章节再拆、短 chunk 合并做兜底。

**B2 dense 检索和 BM25 各自的强弱？为什么要 hybrid？**

> dense（bge-small-en-v1.5 双塔）抓语义同义改写，但对精确术语、版本号、错误码
> 这类字面信号弱；BM25 相反。企业 query 两类都有。我的消融正好是证据：
> 该语料上 BM25 doc_hit@5 0.80 强于 vector-only 0.60——因为 external query
> 一半来自真实用户提问，关键词信号强。hybrid RRF 融合后保住 0.80 且
> gold_doc_recall@5 最高（0.79）。

**B3 RRF 是什么？为什么不用加权分数融合？**

> Reciprocal Rank Fusion：每路按排名贡献 1/(k+rank) 再求和。选它因为它只用排名
> 不用分数——dense 的余弦相似度和 BM25 分数量纲完全不同，直接加权需要调归一化
> 和权重两组超参；RRF 无需校准、对单路异常分数鲁棒，是 hybrid 的业界默认起点。

**B4 bi-encoder 和 cross-encoder 的区别？为什么 rerank 理论上有用、你这里没用？**

> bi-encoder 把 query 和文档独立编码成向量，便宜可索引，但交互信息有损；
> cross-encoder 把 (query, doc) 拼一起过模型，能建模词级交互，精度高但只能
> 对 top-k 重排。理论上"召回靠双塔、精排靠交叉"是标准两阶段。我的实测里
> bge-reranker-base 反而把 doc_hit@5 从 0.80 拉到 0.78——假设是通用域 reranker
> 不适配该语料 + query 偏关键词。所以我不声称 rerank 收益，这恰好说明
> rerank 不是免费午餐，需要按域验证。

**B5 embedding 模型怎么选的？**

> 约束优先：无 API key、CPU 可跑、英文语料 → bge-small-en-v1.5。
> 它在 MTEB 上是同尺寸性价比标杆。正式评测禁用 mock/hash embedding，
> 这是 headline eligibility 合约强制的。

## 生成与引用层

**B6 怎么防止 LLM 编造引用？**

> 结构上让编造不可能：生成器输出 claims + supporting_chunk_ids 的结构化 JSON，
> citation binder 校验每个 id 必须存在于本次的 ContextPack——编造的 id 直接被
> 拦截丢弃，有专门的 fake-citation 单测。外部真实 run 上 citation_valid=1.00。
> 但我会主动补一句：这是结构有效性，引用是否真支持 claim 要靠人工审计/judge，
> hard-negative run 证明两者可以背离（valid=1.0 但 grounded=0）。

**B7 structured output 解析失败怎么处理？**

> parser 有 fallback 链：严格 JSON 解析 → 宽松提取 → 失败则按 system_error
> 处理而不是把原始文本透传给用户。prompt 和 parser 由同一执行者同步演化，
> prompt 改动导致 parser 测试挂掉必须同步修——这是计划里写死的协作规则。

**B8 context assembly 做了什么？**

> 去重（同 chunk 多路召回）、token 预算控制、同文档数量上限（source diversity，
> 防单文档垄断上下文）、并把 citation 所需元数据（doc_id/section/行号）随 chunk
> 打包，让下游 binder 不需要回查。

## 信任控制层

**B9 evidence gate 怎么判定证据不足？**

> 多信号：存活 chunk 数为零、top rerank 分低于阈值、支持 chunk 数不足、
> query 实体未命中。判定不足时分流：若是权限导致的不足直接拒答（不许 rewrite
> 绕权限），只有检索弱才进 recovery。阈值当前是未校准的保守值——这正是
> false_refusal 0.46 的主因，Q2 第一阶段就是做阈值扫描画 trade-off 曲线。

**B10 refusal 优先级为什么是 permission > conflict > deprecated > answer/no_evidence？**

> 按错误成本排序：把受限内容答出去是安全事故，必须最先拦；冲突时强行给唯一
> 结论会误导决策，所以其次；deprecated 还能带警示输出。优先级是确定性代码
> 不是 prompt 约定，模型说什么都改变不了分流。

**B11 ACL 过滤放在检索前还是检索后？trade-off 是什么？**

> 我放在检索后、生成前（post-retrieval filter），并且二次检索后重新过一遍。
> 检索前过滤（query 时带 filter）更省且无侧信道，但需要索引支持所有权限维度
> 组合；检索后过滤实现简单、策略可独立演化，代价是受限文档可能占据 top-k
> 名额挤掉干净证据——这正是我测出的 F2 失败模式（deprecated/restricted 邻居
> 触发过度拒答），所以 Q2 的动作空间里有 metadata-filtered re-retrieval。
> 能把自己选择的代价讲成实测失败模式，比背标准答案有说服力。

## Agent 层

**B12 你怎么定义 Agent？你的系统算 Agent 吗？**

> 我用窄定义：根据运行时观察自主选择下一步动作的系统。按这个定义，固定
> pipeline 不是 agent，我的系统是最小 agent——evidence gate 失败时它自主决定
> 重写并二次检索还是放弃。我刻意不叫它 autonomous agent：动作空间封闭、
> 预算一轮、不可绕策略门。我认为企业可部署的只有这种受约束自主性，
> 而且它可证伪——我实测它当前零增益并能解释为什么（F5）。

**B13 为什么限制最多一轮重写？多轮反思不是更强吗？**

> 多轮自我反思的成本/延迟无界、行为不可审计，且每多一轮就多一次绕过策略的
> 机会面。一轮是"最小可量化"的设计：足以验证 recovery 是否有价值，不足以
> 失控。实测一轮无增益的根因是触发面被策略路径挤压，所以正确的下一步是
> 校准 gate 和扩展动作类型（Q2 设计），而不是加轮数。

**B14 （Q2 后）什么是 trajectory evaluation / 逐动作归因？**

> agent 的失败常常"看起来像成功"：格式正确但语义错误、无效动作、绕路。
> 所以不能只评终态，要评轨迹：每个动作记 trigger/accept/success/false-recovery
> 四个计数，独立报告。配 pass^k（k 次重复全对才算过）度量非确定性下的可靠性。

**B15 （Q2 后）LLM 进决策环，怎么保证安全？**

> 三层：动作白名单按诊断类型限定合法集合；validator 代码强制预算、不可绕 gate、
> filters 只收紧不放宽；LLM 提议非法时拒绝并 fallback 到规则控制器——
> 最坏情况整体退化为规则版。安全性来自结构，不来自模型听话。

## 评测层

**B16 hit@k、MRR、recall@k 的区别？**

> hit@k：gold 是否进前 k（二值）；MRR：第一个 gold 的排名倒数均值，对"排第 1
> 还是第 5"敏感；recall@k：多 gold 时前 k 覆盖了几成。我同时报 chunk 级和
> doc 级——chunk 级严格但受切分粒度影响，doc 级更稳。另外强调：这些是检索
> 指标，不是答案准确率，报告里专门注明不得混用。

**B17 为什么不用答案相似度（BLEU/ROUGE/embedding 相似度）评答案？**

> 相似度度量措辞不度量事实，且无法防参数化记忆作弊——模型背过语料就能拿分。
> grounded_correctness 要求正确 + 引用合法 + 引用支持 claim，背书给不出合法
> 引用。实测 direct_llm raw 0.20 / grounded 0.00 就是这个设计在工作。

**B18 什么是评测数据污染？你怎么处理？**

> 评测语料进过模型训练集，导致分数反映记忆而非能力。公开语料几乎必然污染
> ——FastAPI 文档大概率在 DeepSeek 训练分布里。我不假装没有，而是显式隔离：
> headline 用 grounded 指标（记忆给不出引用），raw−grounded 差值作为
> parametric_leakage_gap 单独报告，报告有固定污染分析章节。彻底解法是
> 私有/held-out 语料，列在后续路线。

**B19 LLM-as-judge 有什么风险？你怎么用？**

> 三大风险：自偏好（judge 与被评是同模型则偏高）、未经验证的 judge 只是观点、
> 位置/冗长偏置。我的协议：judge 模型必须与系统模型不同家族；先做 25–40 条
> 人工锚点，judge 在锚点上的 binary agreement 过选型门（锚在人工自一致率上）
> 才许上岗；与 RAGAS/DeepEval 同锚点对比选型；judge 数字永远带 judge_based
> 标签，不与人工数字混写。

**B20 false refusal 和 false answer 的 trade-off 怎么选工作点？**

> 先承认这是一条曲线不是一个点。企业场景成本不对称：答错权限/合规/版本问题
> 是事故，拒答只是不便，所以 Q1 默认 fail-closed（false_answer=0 优先）。
> 工作点选择应该基于阈值扫描画出的曲线 + 业务成本比，而不是挑 headline
> 最好看的点。我目前的点偏保守（false_refusal 0.46），校准是下一阶段主任务。

## 安全与工程

**B21 什么是 indirect prompt injection？RAG 为什么特别脆弱？**

> 恶意指令不在用户输入里，而在被检索的文档里——RAG 把语料当可信源，检索
> 等于替攻击者把载荷送进上下文，这是 OWASP LLM Top 10 的第一位。我的系统
> 四道 gate 是确定性代码，天然免疫"用自然语言说服 gate"类攻击，但语义层
> （冒充受限内容、拒答抑制）拦不住，所以设计了 10 条成对对照的红队 split
> 实测（投毒索引 vs 干净索引），结果如实报告。

**B22 mock 在你项目里的合法边界？**

> mock embedding/reranker/LLM 只用于 CI、单测、smoke test 和无 key 启动。
> 任何 mock 产出不得进正式指标——这不是纪律是代码：run summary 带
> mock_used/headline_eligible 字段，有单测守着，mock run 想标 headline
> eligible 会挂测试。

------

## 通用应答原则

1. 数字永远自己先说，不要等面试官翻出来——主动权在先说的人手里。
2. 每个负结果三段式：现象（带数字和 run_id）→ 根因（带 trace 证据或双假设）→ 下一步（已排序）。
3. 绝不说的话：agentic 提升了性能；hard negative 鲁棒；reranker 改善了检索；
   citation accuracy 100%；raw correctness 当系统质量；"调一调就能上去"。
4. 被问到没测过的东西，标准句式："我只引用跑出来的数字，这个还没测，
   我能讲的是机制判断和实验设计。"
