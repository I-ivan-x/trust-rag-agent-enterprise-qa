# 工程知识补课清单（Q1 全程 + Q2 规划范围）

用法：本清单覆盖项目做完 Q2 所涉及的全部工程知识，按领域分组。
每项标注**项目落点**（你在哪段代码/文档里已经"用过它"）和**深度要求**：

```text
A = 面试必须能脱稿讲清原理、取舍和本项目的实测证据（配 INTERVIEW_QA 题号）
B = 能准确解释概念、说出为什么这么选，不要求推导细节
C = 知道它存在、是什么、什么时候该去查
```

补课顺序见文末"最小补课路径"——按 Q2 阶段倒排，先学马上要用的。

------

## 1. 检索与 IR 基础

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| 倒排索引与 BM25（TF-IDF→BM25 的演进、k1/b 参数直觉） | Whoosh keyword_store | A | B2 |
| 稠密检索 / bi-encoder 原理（双塔、余弦相似、为什么有损） | embedding_service + Qdrant | A | B2/B4 |
| cross-encoder 重排（与双塔的本质区别、两阶段架构） | bge-reranker + 消融负结果 | A | B4 |
| RRF 及融合方法对比（vs 加权分数、vs learned fusion） | hybrid_retriever | A | B3 |
| 向量索引原理：HNSW 是什么、近似检索的召回/速度 trade-off | Qdrant 内部 | B | 能解释"为什么向量库不做精确暴力搜索" |
| chunking 策略谱系（固定窗口/递归/语义/结构感知） | section-aware chunker | A | B1 |
| MTEB / BEIR 是什么、embedding 选型怎么看榜 | bge-small-en-v1.5 选型 | B | B5 |
| 评测指标：hit@k / MRR / recall@k / nDCG | eval/metrics.py | A | B16（nDCG 项目没用，B 级） |

## 2. LLM 应用基础

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| prompt 设计基础（指令/上下文/输出格式三段、few-shot） | prompts.py、judge prompt | A | 能讲 judge prompt 为何镜像人工规则 |
| structured output / JSON mode / 解析 fallback 链 | output_parser.py | A | B7 |
| temperature 与采样（为什么 judge/controller 用 0） | judge 协议、llm_controller | B | 能讲非确定性与 pass^k 的关系 |
| token、上下文窗口、context budget 管理 | context_assembler | A | B8 |
| OpenAI-compatible API 约定（messages、流式、错误处理） | llm_client.py | B | |
| LLM 成本估算（输入/输出计价、调用量预算） | ROADMAP 预算节 | B | 能复述 Q2 预算怎么估的 |
| 参数化记忆 vs 检索增强（为什么 RAG、什么时候不需要 RAG） | 污染分析章节 | A | B17/B18 |

## 3. Agent 工程

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| workflow agent vs autonomous agent 的谱系与定义之争 | §1.2 计划 + ADR-004 | A | B12 |
| 动作空间设计、停止条件、预算控制 | Q2_AGENT_DESIGN | A | B13/B15 |
| guardrail / validator 模式（LLM 提议、代码执法） | validator V1–V7 | A | B15 |
| trajectory evaluation、per-action 归因 | Q2 §8 | A | B14 |
| pass^k 与 agent 非确定性（τ-bench 引入的可靠性度量） | Q2 打包决议 C | A | B14 |
| ReAct / Reflexion 等经典 agent 模式（知道为何 Q1 拒绝多轮反思） | ADR-004 rationale | B | 能对比"反思循环"与"受控恢复"的审计差异 |
| LangGraph 核心概念（节点/边/state/checkpoint） | framework mapping 触发器项 | B | 能把自研 orchestrator 映射到 LangGraph 概念 |
| MCP（Model Context Protocol）是什么、解决什么 | 打包决议 D（看心情项） | C | |
| multi-agent 编排（知道为什么 Q1/Q2 都明确不做） | N-08 禁令 | C | |

## 4. 评测方法论（本项目的灵魂，优先级最高）

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| grounded scoring 设计（为什么答对≠得分） | metrics.py + ADR-002 | A | B17 |
| 训练数据污染：成因、检测信号、隔离手段 | 污染分析章节 + leakage_gap | A | B18 |
| 评测集构建：作者隔离、泄漏检查、**双向边界教训** | EVAL_PROTOCOL + ADJUDICATION §6 | A | 能讲 hard-negative split 怎么翻车的 |
| hard negative 的概念（检索训练/评测两种语境） | hard_negative corpus | B | |
| LLM-as-judge：偏置类型（自偏好/位置/冗长）、人工锚定验证 | JUDGE_PROTOCOL | A | B19 |
| RAGAS / DeepEval / TruLens：各自指标体系与适用场景 | judge 三方对比 | B | 能说出 faithfulness 和你的 grounded 的异同 |
| 标注一致性：Cohen's kappa、自一致率、为什么 kappa 防基率虚高 | JUDGE_PROTOCOL §4 | B | 能解释 agreement 0.9 在 90% 单边分布下为何可能无意义 |
| bootstrap 置信区间、小样本 caveat | 锚点 n≤40 的 CI 声明 | B | |
| 消融实验设计：对照、单变量、claim-only-what-you-measure | baselines 分层 + ADR-006 | A | Q4（硬质疑题） |
| eval-in-CI / 回归门禁 | ROADMAP P2-06 | B | |
| A/B 成对对照设计 | 红队 clean/poisoned 成对 run | B | 能讲为什么没有干净对照就无法归因 |

## 5. AI 安全与治理

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| OWASP LLM Top 10，重点 LLM01 prompt injection | REDTEAM_INJECTION_SPLIT | A | B21 |
| direct vs indirect injection、RAG 投毒路径 | 红队 10 条设计 | A | B21 |
| fail-closed / fail-open 设计哲学与成本不对称 | ADR-001 | A | B20、Q1（硬质疑） |
| defense-in-depth（为什么确定性 gate 免疫一类攻击而语义层不免疫） | RT-006 vs RT-005 预期 | A | 能讲两条 case 预期差异的原因 |
| 最小权限原则在 RAG 的体现（ACL 过滤位置 trade-off） | acl_gate + B11 | A | B11 |
| NIST AI RMF / EU AI Act 大图景（治理框架长什么样） | NIST 映射触发器项 | C | |
| 数据合规意识（公开语料 license、来源声明） | README 数据边界节 | B | |

## 6. Python 与服务工程

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| Pydantic v2（schema、校验、序列化） | app/schemas/* | A | |
| FastAPI（路由、依赖注入、lifespan、Swagger） | app/api/* | A | |
| pytest（fixture、参数化、conftest、mock/patch） | 55 个测试文件 | A | |
| uv / pyproject / ruff 工具链 | 工程化配置 | B | |
| dataclass vs Pydantic 的选择 | real_pipeline.py 用 dataclass | B | |
| lru_cache 做单例/惰性加载的模式与坑 | real_pipeline 的 retriever 缓存 | B | 缓存了配置怎么办？ |
| 结构化日志 / JSONL 作为数据交换格式 | tracing + run 产物 | B | |
| 类型注解与 `from __future__ import annotations` | 全代码库 | B | |

## 7. 可观测性与交付

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| trace 设计：span 概念、trace schema 由消费方倒推（ADR-008 教训） | tracing.py + 审计被阻事故 | A | 能讲 artifact gap 怎么发现的 |
| OpenTelemetry GenAI 语义约定（agent span / tool span 标准化） | OTel 触发器项 | C | |
| Docker / docker-compose（镜像分层、volume、服务编排） | C1-02 | B | 模型权重为什么挂载而不打进镜像 |
| Makefile / 任务编排 | W7 | C | |
| Git 工程纪律（分支、commit 规范、tag/release） | 全程 | B | |
| 可复现性：seed 控制、配置冻结、run_id 追溯 | overlay seed=42、run inventory | A | 能讲"被报告引用的 run 必须可追溯"的实现 |

## 8. 统计与实验素养（贯穿）

| 知识点 | 项目落点 | 深度 | 自查 |
| --- | --- | --- | --- |
| n<5 不报百分比的理由（小样本比例的方差） | 报告原则 | B | |
| 比例的置信区间（Wilson/bootstrap 直觉即可） | judge 锚点 CI | B | |
| 多重比较直觉（阈值扫描挑最好点的过拟合风险） | gate calibration 选点纪律 | B | 为什么"挑 headline 最好看的点"是作弊 |
| 幸存者偏差（审计只覆盖已作答的 26%） | CITATION_AUDIT_GUIDE §7 | B | |

------

## 最小补课路径（按 Q2 时间倒排，先学马上要用的）

```text
立刻（Q1 收尾期间，~3 个晚上）：
  4 类全部 A 级（grounded/污染/泄漏教训/消融纪律）——这是面试核心，
  且全部能用自己项目的实测当例子，学习成本最低。
  配套：把 INTERVIEW_QA B16–B20 脱稿讲一遍给自己听。

Q2-W1 前（gate calibration 需要）：
  8 类：多重比较直觉、trade-off 曲线选点纪律。
  5 类：fail-closed 哲学（ADR-001 重读一遍即可）。

Q2-W4 前（judge 需要）：
  4 类：LLM-as-judge 偏置、kappa、bootstrap；
  跑一遍 RAGAS 和 DeepEval 的 quickstart（各 1 小时，有手感即可）。

Q2-W6 前（红队需要）：
  5 类：OWASP LLM01 原文 + 一篇 indirect injection 实例分析。

Q2-W7 前（agent 需要）：
  3 类全部 A 级；LangGraph 概念过一遍官方 tutorial（不写码，看懂概念）。

求职触发时：
  3 类 C 级（MCP）、7 类 C 级（OTel）补到 B 级；
  5 类 NIST/EU AI Act 大图景看一篇综述。
```

**学习方法建议**：每个 A 级知识点的检验标准不是"看懂了"，而是能用
"概念一句话 + 本项目怎么做的 + 实测数字"三段式讲 60 秒（INTERVIEW_QA
第二部分就是按这个格式写的范本）。你的优势是每个知识点在项目里都有
真实落点——补课实质是把"已经做对的事"补上"为什么对"的理论名字。
