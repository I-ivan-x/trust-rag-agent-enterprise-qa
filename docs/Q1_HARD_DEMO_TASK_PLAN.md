# Q1 Hard Demo Task Plan

项目名称：Trustworthy Enterprise Document RAG-Agent QA System
短名：TrustRAG Enterprise QA
Repo 建议名：trust-rag-agent-enterprise-qa
版本：v0.3-q1-hard-demo-plan-freeze
执行模式：单代码执行者模式
代码执行者：Codex
非代码协作者：Claude
最终验收者：Project Owner

------

## 0. 本版计划的核心修订

本计划是 Q1 Hard Demo 的正式冻结执行版，由 v1 按 v1.1 patch 整合而成，重点修正以下结构性风险：

1. 避免“自产语料 + 自产评测”的循环验证。
2. Mock-first 只用于 CI、单测和 smoke test，不用于正式评测数字。
3. 正式评测必须使用真实 embedding、真实 reranker、真实 LLM。
4. 真实 reranker 进入 Q1 P0；如果真实 reranker 未完成，不允许讲 rerank 提升。
5. 加入 public external corpus 和 hard negatives，避免小语料导致 baseline 对比失真。
6. 保留 RAG-Agent 命名，但加入最小 agentic evidence recovery loop。
7. Week 4 设置强制砍单检查点，确保评测和失败分析不会被挤掉。
8. 删除 Q1 的 ask_clarification response mode，避免没有模块负责的问题。
9. prompt 与 output parser 由 Codex 统一实现和迭代，Claude 只提供 prompt 设计建议。
10. 最终叙事从“我搭了很长链路”转向“我如何证明它比 naive RAG 更可信，以及它在哪里仍然失败”。

------

# 1. 项目定位

## 1.1 项目目标

本项目不是普通 chatbot wrapper，也不是简单“向量检索 + 拼 prompt”的知识库问答，而是一个面向企业内部文档的可信 RAG-Agent 问答系统。

Q1 Hard Demo 的目标是做出一条完整、可运行、可评测、可追踪、可展示的可信 RAG-Agent 主链路：

```text
文档结构化解析
→ section-aware chunking
→ real embedding retrieval
→ BM25 retrieval
→ RRF hybrid retrieval
→ real reranker
→ evidence gate
→ agentic evidence recovery loop
→ context assembly
→ grounded answer generation
→ citation binding
→ citation verification v1
→ ACL gate
→ document state gate
→ refusal controller
→ trace logging
→ automated evaluation
→ failure analysis
→ FastAPI / Swagger demo
```

Q1 的最终目标不是“看起来像企业级系统”，而是：

> 本地可运行、可评测、可追踪，能展示 citation / refusal / document state gate / ACL gate / real rerank / agentic evidence recovery / baseline comparison / failure analysis 的可信企业文档 RAG-Agent 工程项目。

------

## 1.2 为什么仍然保留 Agent

项目名保留：

```text
Trustworthy Enterprise Document RAG-Agent QA System
```

但必须避免“Agent 超卖”。本项目中的 Agent 不是多角色人格代理，也不是自由规划式 autonomous agent，而是一个 **workflow-based agentic retrieval system**。

Q1 最小 agentic 环节定义为：

```text
Initial Retrieval
→ Evidence Gate
→ if evidence insufficient:
      Query Rewrite Node
      Second-pass Retrieval
      Rerank Again
      Evidence Gate Again
→ Answer or Refusal
```

该 agentic loop 必须满足：

- 只有 evidence insufficient 时触发；
- 最多重写 1 次；
- 最多二次检索 1 轮；
- 必须有停止条件；
- 必须写入 trace；
- 必须在 eval 中统计 recovery 成功率；
- 不能无限循环；
- 不能绕过 ACL gate；
- 不能用 LLM 自行编造证据；
- 二次检索后仍证据不足，必须拒答。

这个最小 agentic loop 是项目名中 “Agent” 的依据。

------

## 1.3 最终面试叙事

最终不要主讲：

```text
我实现了很多模块：ingestion、retrieval、rerank、citation、refusal、trace、eval。
```

而要主讲：

```text
我把企业文档 RAG 的可信性拆成 retrieval correctness、citation support、refusal behavior、state/ACL compliance 和 auditability 五个维度。

为了避免循环验证，我将评测分为 synthetic fixture eval、public external eval 和 hard negative eval。

为了避免 mock 数字失效，正式评测使用 real embedding、real reranker 和 real LLM。

我比较了 direct LLM、vector only、BM25 only、hybrid RRF、hybrid RRF + rerank、final gated agentic system。

最后用 failure taxonomy、false refusal vs false answer trade-off、citation support audit 说明系统在哪些情况下更可信，以及在哪些情况下仍然失败。
```

------

# 2. 协作原则

## 2.1 单代码执行者原则

所有代码、测试、脚本、Docker、依赖配置、API、CI/工程化文件，统一由 Codex 负责修改和落地。

Claude 不直接修改 repo 代码，不直接负责：

```text
app/**/*.py
tests/**/*.py
scripts/**/*.py
Dockerfile
docker-compose.yml
pyproject.toml
ruff.toml
pytest.ini
```

原因：

- 避免 schema 不一致；
- 避免 import path 断裂；
- 避免测试不可控；
- 避免 merge 冲突；
- 避免 prompt 与 output parser 脱节；
- 避免代码能写但主链路串不起来。

------

## 2.2 Claude 的职责边界

Claude 只负责非代码内容：

| 类型           | 内容                                                         |
| -------------- | ------------------------------------------------------------ |
| Synthetic 语料 | Northstar Cloud fixture corpus 初稿                          |
| Manifest       | corpus manifest 初稿                                         |
| 规则           | ACL policy、document state policy、evidence policy、refusal policy、citation policy |
| 评测集         | eval query 初稿，但必须遵守 author isolation 原则            |
| 文档           | README 初稿、TECHNICAL_DESIGN 初稿、EVALUATION_REPORT 初稿、FAILURE_ANALYSIS 初稿 |
| 审查           | schema review、eval case review、failure case review、citation audit guideline |
| 面试材料       | INTERVIEW_QA、DEMO_SCRIPT、DEMO_VIDEO_SCRIPT                 |

Claude 不负责正式评测数字，不负责代码，不负责真实模型集成。

------

## 2.3 Codex 的职责边界

Codex 负责所有可执行交付：

| 类型         | 内容                                                         |
| ------------ | ------------------------------------------------------------ |
| 工程骨架     | FastAPI、目录结构、pyproject、pytest、ruff、配置系统         |
| Schema       | Pydantic models、枚举、错误码、ID 生成                       |
| 数据面       | loader、parser、metadata extractor、chunker、ingest script   |
| 公开语料     | public external corpus 下载、清洗、manifest 生成             |
| 索引面       | sentence-transformers embedding、Qdrant、Whoosh、index rebuild |
| 查询面       | retriever、RRF、real reranker、context assembler             |
| Agentic loop | query rewrite、second-pass retrieval、停止条件、trace        |
| 控制面       | state gate、ACL gate、evidence gate、citation verifier、refusal controller |
| 生成面       | real LLM client、MockLLM、prompt integration、output parser、answer generator、citation binder |
| API          | chat、ingest、documents、traces、health                      |
| 评测         | baselines、metrics、runner、report generator、failure export |
| 可观测       | JSONL trace、trace linkage                                   |
| 交付         | Docker、Makefile、smoke test、integration tests              |

------

## 2.4 Prompt 迭代权限

prompt 与 output parser 必须共同演化，因此：

- Codex 负责 `prompts.py`、`output_parser.py` 和 integration。
- Claude 可以起草 prompt design guideline。
- 但最终 prompt 格式、JSON schema、parser fallback、测试样例由 Codex 统一落地。
- 如果 prompt 修改导致 parser 测试失败，Codex 必须同步修复。

------

# 3. Q1 范围冻结

## 3.1 Q1 P0 必做范围

| 编号  | 模块                                   | 说明                                                      |
| ----- | -------------------------------------- | --------------------------------------------------------- |
| P0-01 | FastAPI 项目骨架                       | 提供 API 和 Swagger demo                                  |
| P0-02 | Pydantic schemas                       | Document、Chunk、Citation、Chat、Trace、EvalCase          |
| P0-03 | Markdown/TXT ingestion                 | 本地文档目录批量导入                                      |
| P0-04 | Front matter metadata                  | status、version、access、role、owner、tags                |
| P0-05 | Section-aware chunking                 | 按 H1/H2/H3 切分，保留 section_path 和 line range         |
| P0-06 | Synthetic fixture corpus               | 用于功能回归，不作为 headline metrics                     |
| P0-07 | Public external corpus                 | 用于正式外部效度评测                                      |
| P0-08 | Hard negative corpus                   | 用于检索鲁棒性和版本相似性测试                            |
| P0-09 | SentenceTransformerEmbedding           | 本地真实 embedding，正式 retrieval eval 使用              |
| P0-10 | MockEmbedding                          | 只用于单测和 smoke test                                   |
| P0-11 | Qdrant vector retrieval                | dense retrieval                                           |
| P0-12 | Whoosh BM25 retrieval                  | keyword retrieval                                         |
| P0-13 | RRF hybrid retrieval                   | vector + BM25 融合                                        |
| P0-14 | BGE reranker                           | 真实 reranker，正式消融必须使用                           |
| P0-15 | MockReranker                           | 只用于 fallback 和单测                                    |
| P0-16 | Context assembler                      | 去重、限长、source diversity、citation metadata           |
| P0-17 | LLM client interface                   | 支持 MockLLM 和 real LLM                                  |
| P0-18 | Real LLM final run                     | Week 6 正式评测至少跑一次                                 |
| P0-19 | Answer generator                       | 结构化生成 claims + supporting_chunk_ids                  |
| P0-20 | Citation binder                        | claim 绑定 chunk citation                                 |
| P0-21 | Citation verifier v1                   | 规则版校验 citation validity 与最小 support               |
| P0-22 | Document state gate                    | active / draft / deprecated / archived                    |
| P0-23 | ACL mock gate                          | role / department / clearance 过滤                        |
| P0-24 | Evidence gate                          | 证据不足时拒答或触发 recovery                             |
| P0-25 | Agentic evidence recovery              | 证据不足时 query rewrite + 二次检索一次                   |
| P0-26 | Refusal controller                     | answer / no_evidence / permission / deprecated / conflict |
| P0-27 | JSONL trace logging                    | 每次 query 可追踪                                         |
| P0-28 | Eval author isolation protocol         | 语料作者与 eval query 作者流程隔离                        |
| P0-29 | Fixture eval                           | 36 条，功能回归，不进 headline                            |
| P0-30 | External eval                          | 50 条，正式报告 headline 主依据                           |
| P0-31 | Hard negative eval                     | 20 条，检索与引用鲁棒性专项                               |
| P0-32 | Baseline comparison                    | retrieval tier + end-to-end tier 分层                     |
| P0-33 | run_eval.py                            | 自动评测脚本                                              |
| P0-34 | Manual citation support audit          | 40 条 claim 人工抽样 citation support 判断                |
| P0-35 | False refusal vs false answer analysis | 拒答阈值 trade-off 分析                                   |
| P0-36 | Failure taxonomy                       | 系统失败类型分析                                          |
| P0-37 | Week 4 scope cut review                | 强制砍单检查点，使用降级线而非删除核心项                  |
| P0-38 | README                                 | 项目说明和快速启动                                        |
| P0-39 | TECHNICAL_DESIGN                       | 技术设计文档                                              |
| P0-40 | EVALUATION_REPORT                      | 评测报告，含污染分析章节                                  |
| P0-41 | FAILURE_ANALYSIS                       | 失败案例分析                                              |
| P0-42 | Docker / docker-compose                | 本地可复现启动                                            |
| P0-43 | Demo script                            | 可演示固定问题                                            |
| P0-44 | Public corpus metadata overlay         | 对 public corpus 叠加 ACL/state/version/conflict metadata |
| P0-45 | Minimal conflict detection             | active-active 同 conflict_group_id 冲突检测               |
| P0-46 | Eval leakage check                     | `check_eval_leakage.py` 标题泄漏与答案句抄写检查          |

------

## 3.2 Q1 P1 可选范围

| 编号  | 模块                            | 说明                                     |
| ----- | ------------------------------- | ---------------------------------------- |
| P1-01 | `/eval` API                     | run_eval.py 优先，API 可后置             |
| P1-02 | trace index                     | JSONL trace 足够，index 可后置           |
| P1-03 | complex planner                 | Q1 只做简单 query rewrite                |
| P1-04 | Streamlit UI                    | Swagger 足够，UI 可后置                  |
| P1-05 | LangGraph wrapper               | 自研 orchestrator 优先                   |
| P1-06 | advanced citation verifier      | Q1 先做规则版 + 人工抽样                 |
| P1-07 | cost dashboard                  | trace 中记录 token 即可                  |
| P1-08 | Docker optimization             | 能启动优先，不追镜像优化                 |
| P1-09 | conflict detection full version | full version 仍 P1，最小版已进 P0-45     |
| P1-10 | ambiguity detector              | Q1 删除 ask_clarification mode，后续再做 |

------

## 3.3 Q1 明确不做范围

| 编号 | 不做项                           | 原因                              |
| ---- | -------------------------------- | --------------------------------- |
| N-01 | PDF 高质量解析                   | 容易被版面、表格、OCR 拖慢        |
| N-02 | Docling                          | Q2 再做                           |
| N-03 | Elasticsearch                    | Q1 用 Qdrant + Whoosh 足够        |
| N-04 | Phoenix / OpenInference 完整接入 | Q1 用 JSONL trace                 |
| N-05 | React 前端                       | 不证明核心可信 RAG 工程能力       |
| N-06 | 真企业 ACL / SSO                 | 没有真实身份系统，mock 即可       |
| N-07 | 多租户                           | Q1 没必要                         |
| N-08 | 自由规划式多 Agent               | Q1 只做 agentic evidence recovery |
| N-09 | 微调                             | 与 Q1 主链无关                    |
| N-10 | K8S                              | 个人项目性价比低                  |
| N-11 | 高并发压测                       | Q1 不是生产服务                   |
| N-12 | 云部署                           | 本地一键启动优先                  |
| N-13 | 自动增量同步                     | Q2 再做                           |
| N-14 | HITL 审批流                      | Q2/Q3 再做                        |
| N-15 | ask_clarification response mode  | Q1 无 ambiguity detector，先删除  |

------

# 4. 语料与评测设计

## 4.1 三类语料

为了避免循环验证，本项目必须维护三类语料，并在报告中分开呈现。

### 4.1.1 Synthetic Fixture Corpus

用途：

- 验证功能；
- 测试 ACL gate；
- 测试 deprecated state gate；
- 测试 conflict handling；
- 测试 citation binding；
- 测试 refusal controller；
- 测试 agentic evidence recovery 是否触发。

特点：

- 可以由 Claude 生成；
- 可以为了触发特定 gate 而设计；
- 不作为最终 headline metrics 的主要依据；
- 在报告中只能称为 controlled fixture evaluation。

冻结规模：

```text
25 篇文档
300–700 chunks
```

如 Week 4 进度落后，可降级到：

```text
20 篇文档
```

------

### 4.1.2 Public External Corpus

用途：

- 提供外部效度；
- 检验系统面对非定制文档时的检索和引用能力；
- 作为最终 EVALUATION_REPORT 的 headline 主依据之一。

候选来源：

```text
GitLab Handbook
Kubernetes documentation
FastAPI documentation
Qdrant documentation
Open-source project docs with versioned pages
```

优先选择：

```text
GitLab Handbook subset
```

选型原则：

- 文档公开；
- 文档结构清晰；
- 有组织规范、API、部署、安全、流程类内容；
- 不为本项目定制；
- 可合法下载、处理和引用；
- README 中说明数据来源和使用边界；
- 优先选择带版本号且近 12 个月内有实质更新的页面；
- 同一主题优先选择新版本页面，降低模型参数化记忆对旧版本文档的补贴。

冻结规模：

```text
60–80 篇公开文档
1000+ chunks
```

如 Week 4 进度落后，可降级到：

```text
40 篇公开文档
600+ chunks
```

------

### 4.1.3 Hard Negative Corpus

用途：

- 增强检索和引用评测难度；
- 防止 BM25 或 vector 在小语料上过早饱和；
- 测试版本相近、标题相似、术语相同但答案不同的场景。

构造方式：

- 相邻版本文档；
- 近似重复 section；
- 相同标题不同状态；
- 相同术语不同限制；
- deprecated 与 active 内容冲突；
- meeting note 与 official doc 不一致；
- FAQ 与 API spec 表述粒度不同；
- public external corpus 中标题相似但答案不同的页面。

冻结规模：

```text
30 对 hard negative pairs
其中 ≥20 对直接取自 public corpus 的相邻版本页面
自产 hard negative ≤10 对
```

如 Week 4 进度落后，可降级到：

```text
20 对 hard negative pairs
12 条 hard negative eval case
```

------

## 4.2 Corpus Source 与 Metadata Overlay 标记

所有 DocumentMetadata 必须包含：

```text
corpus_source: synthetic_fixture | public_external | hard_negative
source_origin: generated | public_web | public_repo
source_license_note: string | null
hard_negative_group_id: string | null
metadata_origin: native | overlay
```

所有 eval result 必须记录 `corpus_source`，并且 final report 必须分开报告：

```text
fixture_eval
external_eval
hard_negative_eval
obfuscated_eval
```

禁止把 synthetic fixture 的结果包装成真实外部评测结果。

### Public corpus metadata overlay

public corpus 的正文保持真实公开来源，不为了门控测试改写文本；但是 `status`、`access_level`、`allowed_roles`、`version`、`superseded_by`、`conflict_group_id` 可以通过 overlay 配置受控叠加。

overlay 配置文件：

```text
data/public_corpus/overlay/metadata_overlay.yaml
```

格式：

```yaml
rules:
  - match: "handbook/security/**"
    access_level: restricted
    allowed_roles: [security, admin]
  - match: "handbook/legal/**"
    access_level: confidential
documents:
  - path: "handbook/engineering/deploy-v1.md"
    status: deprecated
    version: "1.0"
    superseded_by: "handbook/engineering/deploy-v2.md"
defaults:
  status: active
  access_level: internal
seed: 42
```

赋值约束：

- restricted/confidential 占比 15–25%；
- deprecated 占比 10–15%；
- deprecated 标记优先打在确实存在新版本页面的旧版本上；
- overlay 由 seed 控制，重跑 ingest 结果一致；
- 被 overlay 修改过的字段标记为 `metadata_origin=overlay`；
- 报告中如实声明：external eval 的 ACL/state 元数据为受控叠加，文本为真实公开文本。

------

## 4.3 Eval Author / Corpus Author 隔离协议

为避免语料和评测共谋，流程必须这样执行：

```text
1. Corpus Builder 先冻结语料和 corpus_manifest。
2. Eval Author 不直接看全文，只看 manifest、doc title、doc type、tags、section titles、status、access level。
3. Eval Author 按 query 来源优先级编写 query 和 expected_behavior。
4. Codex 基于实际 chunk 结果回填 gold_chunk_ids。
5. Owner 人工抽查 gold_doc_ids 和 gold_chunk_ids。
6. scripts/check_eval_leakage.py 对 eval case 做标题泄漏、答案句抄写、难度分层检查。
7. Eval 数据冻结前必须归档 leakage report；不达标 case 必须改写或降级为 easy 标签。
8. EVALUATION_REPORT 中声明 controlled fixture、public external、hard negative、obfuscated split 的区别。
```

### External eval query 来源优先级

```text
来源 A（≥50%）：真实人类提问
    GitLab forum、Reddit、Stack Overflow、GitHub issues 中
    与所选 public corpus 主题相关的真实问题。
    筛选标准：该问题能被语料中的文档回答。
    记录字段 query_source: real_user_question + 原始链接。
    问题文本可改写脱敏，但保留原始提问的措辞风格。

来源 B（≤50%）：manifest-based 出题
    沿用隔离协议，但必须通过自动泄漏检查。
```

真实问题采集的目标不是凑数量，而是引入缩写、口语化、术语错位和非标准表达，使 external eval 不被标题词匹配饱和。

### 自动泄漏 / 难度检查

新增脚本：

```text
scripts/check_eval_leakage.py
```

检查规则：

```text
检查 1：标题泄漏
    query 内容词与 gold doc title + gold section_path 的重合率 > 0.6
    → 标记 title_leak，要求改写或降级为 easy 标签。

检查 2：答案句抄写
    query 是否为任一 gold chunk 内句子的子串/近似子串。
    字符级相似 > 0.8 → 拒绝该 case。

检查 3：难度分层统计
    输出全集 title_overlap_score 分布。
    external eval 中 title_overlap_score < 0.3 的 query 占比 ≥ 40%。
```

角色建议：

| 环节                          | 负责人                                              |
| ----------------------------- | --------------------------------------------------- |
| synthetic corpus 初稿         | Claude                                              |
| public corpus 选择与下载/整理 | Codex                                               |
| public corpus manifest        | Codex                                               |
| metadata overlay 初稿         | Claude                                              |
| eval query 初稿               | Claude / ChatGPT，但必须遵守隔离协议                |
| 真实问题采集筛选              | Owner + Claude                                      |
| adversarial query 审查        | Owner / ChatGPT                                     |
| gold_chunk_ids 回填           | Codex                                               |
| leakage check                 | Codex                                               |
| gold_chunk_ids 抽查           | Owner                                               |
| final metric 解释             | Owner / ChatGPT                                     |

------

## 4.4 Eval Split 设计

### Eval 总规模

| Split | 条数 | 用途 |
| ----- | ---- | ---- |
| fixture | 36 | 功能回归，不进 headline |
| external | 50 | headline 主依据 |
| hard_negative | 20 | 鲁棒性专项 |
| obfuscated | 15 | agentic loop 专项 |
| 合计 | 121 | |

### Fixture Eval（36 条）

用于功能回归。

| Type | 数量 |
| ---- | ---- |
| single_doc_fact | 6 |
| multi_doc_synthesis | 5 |
| no_evidence | 5 |
| permission_denied | 6 |
| deprecated_doc | 4 |
| conflict_doc | 5 |
| citation_required | 5 |
| 合计 | 36 |

说明：fixture 的大量行为分支已被单元测试覆盖，eval 只需回归确认端到端行为。

### External Eval（50 条，metadata overlay 使能后）

用于正式报告。

| Type | 数量 | 备注 |
| ---- | ---- | ---- |
| fact_lookup | 10 | 来源 A 优先 |
| section_lookup | 6 | |
| multi_doc_synthesis | 8 | |
| citation_required | 8 | |
| no_evidence_or_out_of_scope | 6 | |
| permission_denied | 6 | 依赖 overlay |
| deprecated_doc | 4 | 依赖 overlay |
| conflict_doc | 2 | 依赖 overlay，case study 级 |
| 合计 | 50 | |

### Hard Negative Eval（20 条）

用于检索和引用鲁棒性专项报告。

要求：

- 覆盖相似标题；
- 覆盖相邻版本；
- 覆盖相同术语不同限制；
- 覆盖 active/deprecated 混淆；
- 重点报告 hard_negative_error_rate 与失败类型。

### Obfuscated Eval（15 条）

用于量化 agentic evidence recovery 的专属价值。

构造规格：

```text
规模：15 条
来源：从 external eval 中已被 final_gated 答对的 query 里抽取，
      构造缩写、同义改写、术语错位、口语化变体；
      优先直接使用真实人类提问中天然混淆的表达。
gold：与原 query 相同的 gold_doc_ids / gold_chunk_ids。
计分：只看最终结果 grounded_correctness / 正确拒答，
      不把“是否触发 rewrite”写进 gold。
专属对比：final_gated vs final_agentic。
```

### 报告原则

- n < 5 的类型不单独报百分比；
- n < 5 的类型只做 case study；
- citation 专项至少 20 条；
- refusal 专项至少 20 条；
- external eval 是正式 headline metrics 的主要依据；
- fixture eval 只报告功能回归通过情况；
- hard negative eval 单独报告错误率和失败类型；
- obfuscated eval 单独报告 final_gated vs final_agentic；
- headline answer 指标只使用 grounded_correctness；
- raw correctness 只作为污染分析参考。

------

# 5. Mock 与真实模型策略

## 5.1 Mock 的合法用途

Mock-first 仍然保留，但用途收窄。

Mock 可以用于：

- CI；
- schema 测试；
- 单元测试；
- orchestrator smoke test；
- 无 API key 的本地启动；
- citation fake-id 测试；
- refusal controller 分支测试；
- agentic loop 停止条件测试。

Mock 不可以用于：

- 正式 EVALUATION_REPORT headline metrics；
- retrieval quality 结论；
- citation support 结论；
- rerank ablation 结论；
- 简历数字；
- 面试中作为真实性能展示。

------

## 5.2 Embedding 策略

| 场景                    | Embedding                     |
| ----------------------- | ----------------------------- |
| unit tests              | MockEmbedding / HashEmbedding |
| local default retrieval | SentenceTransformerEmbedding  |
| 中文语料                | bge-small-zh-v1.5             |
| 英文语料                | bge-small-en-v1.5             |
| 高质量可选              | bge-base / bge-m3             |
| hosted 可选             | OpenAI-compatible embedding   |

Q1 P0 要求：

```text
实现 SentenceTransformerEmbedding
正式 retrieval eval 不使用 HashEmbedding 结果作为结论
```

验收标准：

- 不需要 API key；
- CPU 可运行；
- 能对 chunks 和 query 生成真实语义向量；
- 能和 Qdrant 集成；
- `embedding_provider=sentence_transformer` 是正式 eval 默认配置。

------

## 5.3 Reranker 策略

| 场景            | Reranker     |
| --------------- | ------------ |
| unit tests      | MockReranker |
| formal ablation | BGEReranker  |
| fallback        | RRF score    |

Q1 P0 要求：

```text
实现 BGEReranker
```

推荐模型：

```text
BAAI/bge-reranker-base
或其他轻量 cross-encoder reranker
```

如果真实 reranker 未完成：

- 不允许写 rerank improvement；
- 不允许做 rerank ablation；
- README 中只能说 reranker interface 已预留。

------

## 5.4 LLM 策略

### MockLLM 用途

- 测试结构化输出解析；
- 测试 citation binder；
- 测试 refusal controller；
- 无 key smoke test。

### Real LLM 用途

- 生成正式答案；
- 暴露真实 hallucination / unsupported citation 问题；
- 支持 citation verifier 评测；
- 支持 final EVALUATION_REPORT；
- 支持 agentic query rewrite。

### Q1 正式评测要求

Week 6 至少跑一次：

```text
hybrid_final_real_run
```

并保存：

```text
data/eval_runs/{run_id}/results.jsonl
data/eval_runs/{run_id}/traces.jsonl
data/eval_runs/{run_id}/failures.jsonl
data/eval_runs/{run_id}/summary.json
```

正式报告必须明确标注：

```text
mock run: for CI only
real run: used for reported metrics
```

------

# 6. Agentic Evidence Recovery 设计

## 6.1 触发条件

Agentic recovery 只在 evidence gate 判定证据不足时触发。

触发条件示例：

```text
allowed_chunks == 0
OR top_rerank_score < min_top_score
OR support_chunk_count < min_support_count
OR query has specific entities but retrieved chunks miss those entities
```

注意：

- permission denied 不触发 query rewrite；
- ACL 被拦截的证据不能通过 rewrite 绕过；
- archived 文档不能通过 rewrite 被重新引入；
- 如果 evidence insufficient 是因为权限不足，直接 refusal；
- 如果 evidence insufficient 是因为检索弱，才允许 rewrite。

------

## 6.2 Query Rewrite Node

输入：

```text
original_query
first_pass_retrieval_summary
missing_entities
query_type
```

输出：

```text
rewritten_query
rewrite_reason
```

实现策略：

- Week 3 可先规则版；
- Week 4 接真实 LLM rewrite；
- rewrite 不能改变用户意图；
- rewrite 不能加入未出现的新事实；
- rewrite 目标是提升检索召回。

示例：

```text
original: 旧版 token 限流规则现在还有效吗？
rewritten: Auth Service token rate limit current version deprecated v1 v2 refresh token
```

------

## 6.3 Second-pass Retrieval

二次检索流程：

```text
rewritten_query
→ vector retrieval
→ BM25 retrieval
→ RRF fusion
→ real reranker
→ state gate
→ ACL gate
→ evidence gate
```

二次检索最多执行 1 次。

------

## 6.4 停止条件

必须满足以下停止条件：

```text
max_rewrite_rounds = 1
if second_pass_evidence_sufficient:
    proceed to answer
else:
    refuse_no_evidence
```

禁止：

- 无限重写；
- 多轮自我反思；
- 不受控的 tool loop；
- 绕过 gates；
- LLM 自行补证据。

------

## 6.5 Trace 要求

Trace 必须记录：

```text
first_pass_query
first_pass_top_chunks
first_pass_evidence_decision
rewrite_triggered
rewritten_query
rewrite_reason
second_pass_top_chunks
second_pass_evidence_decision
final_decision
```

------

## 6.6 Evaluation 指标

Agentic recovery 不再用 `expected_rewrite` 作为计分字段。rewrite 相关指标全部作为全量 eval run 的观测性统计单独报告：

```text
rewrite_trigger_rate
rewrite_success_rate
second_pass_hit_improvement
second_pass_false_recovery_rate
```

定义：

- rewrite_trigger_rate：多少 query 触发 rewrite；
- rewrite_success_rate：触发 rewrite 后多少 case 从 insufficient 变为 sufficient；
- second_pass_hit_improvement：二次检索是否提升 gold hit；
- second_pass_false_recovery_rate：rewrite 后看似有证据但实际引用不支持的比例。

Agentic loop 的价值不靠“是否按预期触发 rewrite”证明，而靠 obfuscated split 上 `final_gated vs final_agentic` 的 grounded_correctness / 正确拒答差异证明。

------

# 7. Metrics 设计

## 7.1 Retrieval Metrics

保留：

```text
hit@1
hit@3
hit@5
MRR
gold_doc_recall@k
```

新增：

```text
hard_negative_error_rate
deprecated_confusion_rate
second_pass_hit_improvement
```

------

## 7.2 Answer / Citation / Grounded Metrics

end-to-end 系统的 answer 指标必须拆为 raw 与 grounded 两层，并同时报告：

```text
raw_correctness：
    答案与 reference_answer 匹配，不看引用。

grounded_correctness：
    raw_correct
    AND 所有 citation 来自 ContextPack（citation_validity 通过）
    AND 至少一条 citation 经规则版 verifier 判定支持核心 claim。
```

headline 指标只使用：

```text
grounded_correctness
```

答对但引用不支持 = 不得分。参数化记忆无法在 headline 指标上作弊，因为它给不出合法 citation。

raw 与 grounded 之间的差值作为污染分析指标：

```text
parametric_leakage_gap = raw_correctness - grounded_correctness
```

Citation metrics 区分以下指标：

```text
citation_presence
citation_validity
citation_support_accuracy_manual_sampled
unsupported_claim_rate
```

定义：

- citation_presence：该引用时是否给了引用；
- citation_validity：citation 是否来自 ContextPack；
- citation_support_accuracy_manual_sampled：人工抽样判断引用是否真的支持 claim；
- unsupported_claim_rate：answer 中无法被 citation 支持的 claim 比例。

Q1 不声称自动 citation_accuracy 完全可靠。
如果使用规则版 verifier，报告必须写明局限。

人工 citation audit 定标：

```text
40 条 claim
external 20 + hard_negative 10 + fixture 10
单标注者 + 一周后自抽 10 条复标
报告自一致率
```

------

## 7.3 Refusal Metrics

保留并强化：

```text
refusal_accuracy
false_refusal_rate
false_answer_rate
permission_refusal_accuracy
no_evidence_refusal_accuracy
```

新增：

```text
false_answer_vs_false_refusal_tradeoff
```

报告中必须讨论：

- 阈值调高后 false answer 降低但 false refusal 上升；
- 阈值调低后覆盖率提高但 hallucination 风险上升；
- Q1 选择的阈值为什么是合理折中。

------

## 7.4 Agentic Recovery Metrics

新增：

```text
rewrite_trigger_rate
rewrite_success_rate
second_pass_hit_improvement
second_pass_false_recovery_rate
```

这些指标必须单独报告，不能混在普通 retrieval improvement 中。

Agentic loop 的核心量化证据是：

```text
final_gated vs final_agentic on obfuscated split
```

------

## 7.5 Memorization & Contamination Analysis Metrics

EVALUATION_REPORT 必须增加固定章节：

```text
Memorization & Contamination Analysis
```

必须包含：

- direct_llm 在 fixture（模型未见过）与 external（可能背过）上的 raw_correctness 对比；
- 各 end-to-end 系统的 parametric_leakage_gap；
- external corpus 存在训练数据污染的说明；
- headline 结论只基于 grounded_correctness 与 retrieval/citation/refusal 指标；
- answer-only raw_correctness 仅作参考，不作为简历或面试主数字。

------

# 8. Baseline 与 Ablation 设计

## 8.1 Baseline 分层

v1.1 将 baseline 改为两层，避免 7 个系统全部端到端真实 LLM 调用导致人工审核和调试成本超载。

### Retrieval tier

Retrieval tier 不调用 LLM，只计算 hit@k / MRR / gold_doc_recall@k / hard_negative_error_rate。

| System | 描述 | 用途 |
| ------ | ---- | ---- |
| vector_only | real embedding + vector retrieval | 普通向量 RAG baseline |
| bm25_only | BM25 retrieval | 关键词 baseline，作为 retrieval tier 顺手输出 |
| hybrid_rrf | vector + BM25 + RRF | 验证 hybrid retrieval |
| hybrid_rrf_rerank | hybrid + real reranker | 验证 rerank |

### End-to-end tier

End-to-end tier 使用真实 LLM，计算 grounded_correctness / citation / refusal / failure taxonomy。

| System | 描述 | 用途 |
| ------ | ---- | ---- |
| direct_llm | 不检索，直接回答 | 证明裸模型不能可靠回答文档问题，并用于污染分析 |
| final_gated | hybrid + rerank + citation + state/ACL/evidence/refusal | 验证可信控制 |
| final_agentic | final_gated + evidence recovery loop | 验证最小 agentic loop |

------

## 8.2 消融实验要求

必须至少输出：

```text
vector_only vs hybrid_rrf vs hybrid_rrf_rerank
    retrieval tier

direct_llm vs final_gated
    end-to-end tier

final_gated vs final_agentic
    end-to-end tier + obfuscated split
```

如果真实 reranker 未完成：

- 删除 rerank 消融；
- 不允许报告 rerank 提升；
- README 中只能说 reranker interface 已预留。

如果真实 LLM 未完成：

- 只允许报告 retrieval metrics；
- 不允许报告 answer / citation / refusal 的正式结论；
- 不允许写 grounded_correctness headline。

------

## 8.3 成本与人工预算

```text
LLM 调用估算：
    end-to-end：121 case × 3 系统 ≈ 363 次
    + agentic rewrite ≈ 60–80 次
    + 调试余量 ×1.5
    ≈ 700 次调用，每次约 2–4k tokens 输入 / 0.5k 输出。
    使用中档模型，总成本量级在数十元人民币，上限按 ¥200 预算，不构成约束。

Owner 人工时间：
    gold 标签审核：121 条 × 约 2 分钟 ≈ 4 小时（W5）
    真实问题采集筛选：≈ 3 小时（W5，与 Claude 协作）
    citation support 人工抽样审计：40 条 claim，每条约 3 分钟 ≈ 2 小时（W6–W7）
    每周验收 + scope review：≈ 2 小时/周
    合计约 8 周 × 8–10 小时/周内可容纳，留有余量。
```

------

# 9. Response Modes 修订

Q1 只保留以下 response modes：

| Mode               | 触发条件                       |
| ------------------ | ------------------------------ |
| answer             | 证据充足、权限通过、引用合法   |
| refuse_no_evidence | 二次检索后仍证据不足           |
| refuse_permission  | 相关证据存在但当前用户无权访问 |
| warn_deprecated    | 只找到过期文档或需要历史对比   |
| report_conflict    | 检测到 active-active 同组冲突  |
| system_error       | 系统异常                       |

删除：

```text
ask_clarification
```

原因：

- Q1 没有 ambiguity detector；
- 没有模块负责模糊问题判定；
- ambiguous query 只作为 case study，不作为正式 response mode。

## 9.1 Minimal Conflict Detection

`report_conflict` 保留为 P0 response mode，但只实现最小冲突检测。

实现位置：

```text
app/guards/document_state_gate.py
```

触发条件：

```text
过完 state gate 和 ACL gate 后的存活证据 chunks 中，
存在 ≥2 个不同 doc_id，
且它们共享同一 conflict_group_id，
且双方 status == active。
```

行为：

```text
response_mode = report_conflict
列出冲突双方 doc_id 与对应 citation
不强行给唯一结论
```

active vs deprecated 同组共存不算 conflict，走 `warn_deprecated`。
conflict 只处理 active vs active。

## 9.2 决策优先级

Refusal controller 必须按以下优先级决策：

```text
refuse_permission > report_conflict > warn_deprecated > answer / refuse_no_evidence
```

------

# 10. 全局 Definition of Done

## 10.1 可运行

- `uv sync` 能安装依赖；
- `pytest` 能通过；
- `ruff check` 能通过；
- `uvicorn app.main:app --reload` 能启动；
- Swagger UI 可访问；
- `docker compose up` 能启动 API + Qdrant；
- `.env.example` 完整；
- mock 模式可跑 smoke test；
- real 模式可跑正式 eval。

------

## 10.2 可导入

- `python scripts/ingest_corpus.py` 能读取 synthetic fixture corpus；
- 能读取 public external corpus；
- 能读取 hard negative corpus；
- 能生成 `documents.jsonl`；
- 能生成 `chunks.jsonl`；
- chunk 保留 `doc_id`、`chunk_id`、`section_path`、`line_start`、`line_end`、`status`、`version`、`allowed_roles`、`access_level`、`corpus_source`、`hard_negative_group_id`。

------

## 10.3 可检索

- `python scripts/rebuild_indexes.py --embedding-provider sentence_transformer` 能重建真实向量索引；
- Qdrant 可检索；
- Whoosh 可检索；
- RRF 可融合；
- BGE reranker 可重排；
- `python scripts/search_preview.py "query"` 能输出 vector / BM25 / RRF / rerank top-k；
- mock embedding 只用于测试，不用于正式 report。

------

## 10.4 可问答

- `/chat` 能返回标准 `ChatResponse`；
- answer 包含 citations；
- citations 的 chunk_id 必须来自 ContextPack；
- LLM 编造的 chunk_id 会被拦截；
- 无证据时会触发 agentic evidence recovery；
- 二次检索仍无证据时拒答；
- 权限不足、过期文档、冲突文档能触发对应 response mode。

------

## 10.5 可追踪

每次 `/chat` 返回 `trace_id`。
Trace 必须记录：

- original query；
- first-pass retrieval；
- first-pass evidence decision；
- rewrite trigger；
- rewritten query；
- second-pass retrieval；
- second-pass evidence decision；
- rerank results；
- state gate；
- ACL gate；
- citation binding；
- final decision；
- token usage；
- latency。

------

## 10.6 可评测

- `python scripts/run_eval.py` 能运行 fixture eval；
- `python scripts/run_eval.py` 能运行 external eval；
- `python scripts/run_eval.py` 能运行 hard negative eval；
- 支持 direct LLM、vector only、BM25 only、hybrid RRF、hybrid RRF + rerank、final gated、final agentic；
- 输出 retrieval metrics；
- 输出 citation metrics；
- 输出 refusal metrics；
- 输出 agentic recovery metrics；
- 输出 raw_correctness、grounded_correctness、parametric_leakage_gap；
- 输出 obfuscated split 的 final_gated vs final_agentic 对比；
- 输出 per-type metrics；
- n < 5 的类型不报百分比；
- 输出 failures.jsonl；
- 输出 EVALUATION_REPORT.md；
- 输出 FAILURE_ANALYSIS.md。

------

## 10.7 可展示

- README 有架构图、快速启动、demo query、结果示例；
- TECHNICAL_DESIGN 讲清架构和取舍；
- EVALUATION_REPORT 有真实模型 run、分层 baseline 对比、grounded scoring 和污染分析；
- FAILURE_ANALYSIS 有失败案例；
- CITATION_AUDIT.md 有 40 条 claim 人工抽样规则和结果；
- metadata_overlay.yaml 有 public corpus ACL/state/conflict 叠加规则；
- check_eval_leakage.py 输出泄漏检查报告；
- obfuscated_eval.jsonl 用于 final_gated vs final_agentic 对比；
- DEMO_SCRIPT 可用于 Swagger demo；
- INTERVIEW_QA 可用于面试准备。

------

# 11. 目录结构目标

```text
trust-rag-agent-enterprise-qa/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── deps.py
│   │   └── routes/
│   │       ├── chat.py
│   │       ├── ingest.py
│   │       ├── documents.py
│   │       ├── traces.py
│   │       └── health.py
│   ├── core/
│   │   ├── config.py
│   │   ├── enums.py
│   │   ├── errors.py
│   │   ├── ids.py
│   │   └── logging.py
│   ├── schemas/
│   │   ├── document.py
│   │   ├── chunk.py
│   │   ├── retrieval.py
│   │   ├── citation.py
│   │   ├── chat.py
│   │   ├── trace.py
│   │   └── eval.py
│   ├── ingest/
│   │   ├── loader.py
│   │   ├── parser_markdown.py
│   │   ├── parser_text.py
│   │   ├── metadata_extractor.py
│   │   ├── chunker.py
│   │   └── public_corpus_loader.py
│   ├── index/
│   │   ├── embedding_service.py
│   │   ├── vector_store.py
│   │   ├── keyword_store.py
│   │   ├── index_status.py
│   │   └── build_index.py
│   ├── retrieval/
│   │   ├── planner.py
│   │   ├── query_rewriter.py
│   │   ├── vector_retriever.py
│   │   ├── keyword_retriever.py
│   │   ├── hybrid_retriever.py
│   │   └── reranker.py
│   ├── guards/
│   │   ├── document_state_gate.py
│   │   ├── acl_gate.py
│   │   └── evidence_gate.py
│   ├── generation/
│   │   ├── prompts.py
│   │   ├── llm_client.py
│   │   ├── output_parser.py
│   │   ├── context_assembler.py
│   │   ├── answer_generator.py
│   │   ├── citation_binder.py
│   │   ├── citation_verifier.py
│   │   ├── refusal_controller.py
│   │   └── response_formatter.py
│   ├── workflow/
│   │   ├── orchestrator.py
│   │   └── state.py
│   ├── observability/
│   │   ├── tracing.py
│   │   └── cost.py
│   └── eval/
│       ├── dataset.py
│       ├── baselines.py
│       ├── metrics.py
│       ├── runner.py
│       ├── report.py
│       └── citation_audit.py
├── data/
│   ├── sample_corpus/
│   ├── public_corpus/
│   ├── hard_negative_corpus/
│   ├── gold_eval/
│   │   ├── fixture_eval.jsonl
│   │   ├── external_eval.jsonl
│   │   └── hard_negative_eval.jsonl
│   ├── generated/
│   ├── indexes/
│   ├── traces/
│   └── eval_runs/
├── scripts/
│   ├── ingest_corpus.py
│   ├── fetch_public_corpus.py
│   ├── rebuild_indexes.py
│   ├── search_preview.py
│   ├── run_eval.py
│   ├── demo_queries.py
│   └── smoke_test.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evals/
├── docs/
│   ├── Q1_EXECUTION_SPEC.md
│   ├── Q1_HARD_DEMO_TASK_PLAN.md
│   ├── TRUST_POLICY.md
│   ├── EVAL_PROTOCOL.md
│   ├── CORPUS_PROTOCOL.md
│   ├── CITATION_AUDIT_GUIDE.md
│   ├── TECHNICAL_DESIGN.md
│   ├── API_SPEC.md
│   ├── EVALUATION_REPORT.md
│   ├── FAILURE_ANALYSIS.md
│   ├── DEMO_SCRIPT.md
│   ├── INTERVIEW_QA.md
│   ├── DEMO_VIDEO_SCRIPT.md
│   ├── PROJECT_REVIEW.md
│   └── ROADMAP.md
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── pyproject.toml
├── pytest.ini
├── ruff.toml
├── README.md
├── .env.example
├── .gitignore
└── LICENSE
```

------

# 12. Week 0：冻结规格与初始化

核心目标：建立工程骨架、schema、配置、mock-first 基础，并明确 mock 不能用于正式评测。

## 12.1 Week 0 任务清单

| 编号  | 类型   | 负责人 | 任务                                  | 交付物                                                    | 验收标准                                                     |
| ----- | ------ | ------ | ------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------ |
| W0-01 | 代码   | Codex  | 创建 GitHub 仓库并初始化 FastAPI 项目 | repo、`app/main.py`、基础目录                             | 仓库可访问；`uvicorn app.main:app --reload` 可启动；`/docs` 可访问 |
| W0-02 | 代码   | Codex  | 配置 Python 工程化环境                | `pyproject.toml`、`pytest.ini`、`ruff.toml`、`.gitignore` | `uv sync` 成功；`pytest` 可运行；`ruff check` 无错误         |
| W0-03 | 代码   | Codex  | 定义核心 Pydantic schemas             | `app/schemas/*.py`                                        | 支持 JSON 序列化/反序列化；schema tests 通过                 |
| W0-04 | 代码   | Codex  | 定义统一枚举与错误码                  | `app/core/enums.py`、`app/core/errors.py`                 | enum 与 response mode 一致，不包含 ask_clarification         |
| W0-05 | 代码   | Codex  | 定义配置系统                          | `app/core/config.py`、`.env.example`                      | 支持 mock / sentence_transformer / bge_reranker / real_llm 配置 |
| W0-06 | 代码   | Codex  | 定义 ID 生成规则                      | `app/core/ids.py`                                         | doc_id、chunk_id、trace_id、eval_run_id 稳定生成             |
| W0-07 | 代码   | Codex  | 注册 API router 和应用生命周期        | `app/main.py`、`app/api/deps.py`                          | `/health`、`/docs` 正常                                      |
| W0-08 | Schema | Codex  | 预留 corpus source 字段               | schemas                                                   | 支持 `corpus_source`、`source_origin`、`hard_negative_group_id` |
| W0-09 | Schema | Codex  | 预留 agentic recovery 字段            | schemas                                                   | Trace 和 EvalResult 支持 rewrite_triggered、rewritten_query、second_pass_result |
| W0-10 | 语料   | Claude | 编写 5 篇最小 synthetic fixture 文档  | `data/sample_corpus/**`                                   | 只用于 fixture，不用于 headline metrics                      |
| W0-11 | 文档   | Claude | 编写 CORPUS_PROTOCOL 初稿             | `docs/CORPUS_PROTOCOL.md`                                 | 明确 fixture/public/hard-negative 三类语料                   |
| W0-12 | 文档   | Claude | 编写 EVAL_PROTOCOL 初稿               | `docs/EVAL_PROTOCOL.md`                                   | 明确 eval author isolation                                   |
| W0-13 | 评测   | Claude | 编写 5 条 demo eval case              | `data/gold_eval/demo_eval.jsonl`                          | gold_chunk_ids 暂空，Week 1 后回填                           |
| W0-14 | 文档   | Claude | 编写 Q1_EXECUTION_SPEC 初稿           | `docs/Q1_EXECUTION_SPEC.md`                               | 明确 mock 不用于正式指标                                     |
| W0-15 | 文档   | Claude | 编写 SCHEMA_REVIEW_CHECKLIST          | docs                                                      | 覆盖 schema、enum、trace、eval fields                        |
| W0-16 | 代码   | Codex  | 建立 mock-first 占位服务              | `MockEmbedding`、`MockLLM`                                | 仅用于测试和 smoke test                                      |
| W0-17 | 验收   | Owner  | Week 0 验收                           | git commit                                                | `pytest`、`ruff check`、`uvicorn` 全部通过                   |

## 12.2 Week 0 验收命令

```bash
uv sync
ruff check .
pytest
uvicorn app.main:app --reload
```

------

# 13. Week 1：Ingestion + Chunking

核心目标：实现文档从原始文件到结构化 chunk 的完整解析链路，并支持 corpus_source。

## 13.1 Week 1 任务清单

| 编号  | 类型 | 负责人 | 任务                             | 交付物                     | 验收标准                                              |
| ----- | ---- | ------ | -------------------------------- | -------------------------- | ----------------------------------------------------- |
| W1-01 | 代码 | Codex  | 实现文档加载器                   | `app/ingest/loader.py`     | 递归扫描 `.md/.txt`；返回统计                         |
| W1-02 | 代码 | Codex  | 实现 Markdown 解析器             | `parser_markdown.py`       | 解析 front matter、H1/H2/H3、section_path、line range |
| W1-03 | 代码 | Codex  | 实现 TXT 解析器                  | `parser_text.py`           | TXT 也能生成 ParsedDocument                           |
| W1-04 | 代码 | Codex  | 实现元数据提取器                 | `metadata_extractor.py`    | 提取并验证 front matter；补全默认值                   |
| W1-05 | 代码 | Codex  | 实现 section-aware chunker       | `chunker.py`               | 标题分块、长章节拆分、短 chunk 合并                   |
| W1-06 | 代码 | Codex  | 支持 corpus_source 字段          | chunk/document schema      | 每个 chunk 继承 corpus_source                         |
| W1-07 | 代码 | Codex  | 支持 hard_negative_group_id 字段 | chunk/document schema      | hard negative 可追踪                                  |
| W1-08 | 代码 | Codex  | 生成 chunk manifest              | `chunk_manifest.jsonl`     | 记录 chunk_id、doc_id、section_path、line range       |
| W1-09 | 代码 | Codex  | 编写文档导入脚本                 | `scripts/ingest_corpus.py` | 生成 `documents.jsonl` 和 `chunks.jsonl`              |
| W1-10 | 测试 | Codex  | 编写 chunker 单元测试            | `test_chunker.py`          | 覆盖 section split、overlap、metadata 保留            |
| W1-11 | 测试 | Codex  | 编写 ingestion integration test  | `test_ingest_pipeline.py`  | 文档 → chunks → generated files 完整通过              |
| W1-12 | 评测 | Claude | 审查 demo eval                   | `EVAL_CASE_REVIEW.md`      | 确认 gold_doc_ids 和 expected_behavior                |
| W1-13 | 代码 | Codex  | 回填 demo eval 的 gold_chunk_ids | `demo_eval.jsonl`          | 基于实际 chunk_id 回填                                |
| W1-14 | 验收 | Owner  | Week 1 验收                      | git commit                 | ingest 成功，tests 通过                               |

## 13.2 Week 1 验收命令

```bash
python scripts/ingest_corpus.py
pytest tests/unit/test_chunker.py
pytest tests/integration/test_ingest_pipeline.py
```

------

# 14. Week 2：Real Embedding + BM25 + RRF

核心目标：实现真实 embedding 检索、BM25 和 RRF。Mock embedding 只保留给测试。

## 14.1 Week 2 任务清单

| 编号  | 类型 | 负责人 | 任务                                 | 交付物                   | 验收标准                                                |
| ----- | ---- | ------ | ------------------------------------ | ------------------------ | ------------------------------------------------------- |
| W2-01 | 代码 | Codex  | 实现 Embedding 服务接口              | `embedding_service.py`   | 支持 mock、sentence_transformer、openai-compatible      |
| W2-02 | 代码 | Codex  | 实现 MockEmbedding                   | `embedding_service.py`   | 仅用于 tests                                            |
| W2-03 | 代码 | Codex  | 实现 SentenceTransformerEmbedding    | `embedding_service.py`   | CPU 可跑，正式 retrieval eval 默认使用                  |
| W2-04 | 代码 | Codex  | 实现 Qdrant 向量存储                 | `vector_store.py`        | 创建/重建 collection；upsert chunks + vectors + payload |
| W2-05 | 代码 | Codex  | 实现 Qdrant metadata filter          | `vector_store.py`        | 支持 status、access_level、corpus_source、doc_type      |
| W2-06 | 代码 | Codex  | 实现 Whoosh BM25 索引                | `keyword_store.py`       | 构建/重建 index；BM25 search 返回 RetrievedChunk        |
| W2-07 | 代码 | Codex  | 实现 vector retriever                | `vector_retriever.py`    | 输入 query 返回 vector top-k                            |
| W2-08 | 代码 | Codex  | 实现 keyword retriever               | `keyword_retriever.py`   | 输入 query 返回 BM25 top-k                              |
| W2-09 | 代码 | Codex  | 实现 RRF hybrid retriever            | `hybrid_retriever.py`    | 严格实现 `1/(k+rank)`                                   |
| W2-10 | 测试 | Codex  | 编写 RRF 单元测试                    | `test_rrf.py`            | 覆盖排序、去重、单边为空、分数计算                      |
| W2-11 | 测试 | Codex  | 编写 metadata filter 测试            | tests                    | corpus_source、status、access_level filter 可用         |
| W2-12 | 代码 | Codex  | 编写索引重建脚本                     | `rebuild_indexes.py`     | 支持真实 embedding 重建                                 |
| W2-13 | 代码 | Codex  | 编写 search preview CLI              | `search_preview.py`      | 输出 vector/BM25/RRF top-k                              |
| W2-14 | 代码 | Codex  | 实现 index status 检查               | `index_status.py`        | chunks 数、vector 数、Whoosh doc 数一致                 |
| W2-15 | 语料 | Codex  | 开始 public external corpus 获取脚本 | `fetch_public_corpus.py` | 能下载或整理公开 markdown/html 文档子集                 |
| W2-16 | 审查 | Claude | 设计检索测试 query 清单              | `RETRIEVAL_REVIEW.md`    | 覆盖精确词、语义词、过期词、权限词                      |
| W2-17 | 验收 | Owner  | Week 2 验收                          | git commit               | sentence_transformer 检索可用                           |

## 14.2 Week 2 验收命令

```bash
python scripts/ingest_corpus.py
python scripts/rebuild_indexes.py --embedding-provider sentence_transformer
python scripts/search_preview.py "refresh token rate limit"
pytest tests/unit/test_rrf.py
pytest
```

------

# 15. Week 3：Real Reranker + /chat + Citation + Real LLM Interface

核心目标：打通 `/chat`，接入真实 reranker，准备真实 LLM 调用，并建立 citation pipeline。

## 15.1 Week 3 任务清单

| 编号  | 类型 | 负责人 | 任务                                    | 交付物                    | 验收标准                                                  |
| ----- | ---- | ------ | --------------------------------------- | ------------------------- | --------------------------------------------------------- |
| W3-01 | 代码 | Codex  | 实现 RetrievalPlan schema 和 planner v1 | `planner.py`              | 简单策略即可，不做 complex planner                        |
| W3-02 | 代码 | Codex  | 实现 MockReranker                       | `reranker.py`             | 只用于 tests / fallback                                   |
| W3-03 | 代码 | Codex  | 实现 BGEReranker                        | `reranker.py`             | 真实 reranker 可跑                                        |
| W3-04 | 代码 | Codex  | 实现 context assembler                  | `context_assembler.py`    | 去重、token budget、同 doc 限制、citation metadata        |
| W3-05 | 代码 | Codex  | 实现 prompt 模板                        | `prompts.py`              | 与 output parser 同步                                     |
| W3-06 | 代码 | Codex  | 实现 LLM client interface               | `llm_client.py`           | 支持 MockLLM 和 OpenAI-compatible real LLM                |
| W3-07 | 代码 | Codex  | 实现 MockLLM                            | `llm_client.py`           | 仅用于 tests 和 smoke                                     |
| W3-08 | 代码 | Codex  | 实现 real LLM dry-run command           | script 或 test            | 能用环境变量真实调用一次                                  |
| W3-09 | 代码 | Codex  | 实现 structured output parser           | `output_parser.py`        | JSON 解析失败有 fallback                                  |
| W3-10 | 代码 | Codex  | 实现 answer generator                   | `answer_generator.py`     | 输出 claims + supporting_chunk_ids                        |
| W3-11 | 代码 | Codex  | 实现 citation binder                    | `citation_binder.py`      | chunk_id 必须来自 ContextPack                             |
| W3-12 | 测试 | Codex  | 增加 fake citation 测试                 | `test_citation_binder.py` | LLM 编造 chunk_id 时被拦截                                |
| W3-13 | 代码 | Codex  | 实现 response formatter                 | `response_formatter.py`   | 输出标准 ChatResponse                                     |
| W3-14 | 代码 | Codex  | 实现 workflow orchestrator v1           | `orchestrator.py`         | 串联 retrieval → rerank → context → generation → citation |
| W3-15 | 代码 | Codex  | 实现 `/chat` API                        | `chat.py`                 | Swagger 可测                                              |
| W3-16 | 测试 | Codex  | 编写 Chat API 集成测试                  | `test_chat_api.py`        | 正常问答返回 answer + citations                           |
| W3-17 | 文档 | Claude | 编写 PROMPT_DESIGN_REVIEW               | docs                      | 只做审查，不控制代码                                      |
| W3-18 | 验收 | Owner  | Week 3 验收                             | git commit                | `/chat` 可返回带 citation 的答案，BGE reranker 可用       |

## 15.2 Week 3 验收命令

```bash
python scripts/ingest_corpus.py
python scripts/rebuild_indexes.py --embedding-provider sentence_transformer
uvicorn app.main:app --reload
pytest tests/integration/test_chat_api.py
pytest
```

------

# 16. Week 4：Trust Control + Agentic Evidence Recovery + Scope Cut Review

核心目标：实现可信控制、最小 agentic loop、最小冲突检测，并在 Week 4 做强制 scope review。

## 16.1 Week 4 任务清单

| 编号   | 类型 | 负责人 | 任务                                    | 交付物                 | 验收标准                                                       |
| ------ | ---- | ------ | --------------------------------------- | ---------------------- | -------------------------------------------------------------- |
| W4-01  | 代码 | Codex  | 实现 document state gate                | `document_state_gate.py` | active、draft、deprecated、archived 行为明确                   |
| W4-02  | 代码 | Codex  | 实现 ACL gate                           | `acl_gate.py`          | role、department、clearance 生效                               |
| W4-02b | 代码 | Codex  | document_state_gate 增加最小冲突检测    | `document_state_gate.py` | active-active 同 conflict_group_id 触发 report_conflict        |
| W4-03  | 代码 | Codex  | 实现 evidence gate                      | `evidence_gate.py`     | 支持 top score、support count、entity miss 判断                |
| W4-04  | 代码 | Codex  | 实现 query rewriter                     | `query_rewriter.py`    | 规则版可用；可切换 LLM rewrite                                 |
| W4-05  | 代码 | Codex  | 实现 second-pass retrieval              | orchestrator           | 最多二次检索 1 轮                                              |
| W4-06  | 代码 | Codex  | 实现 rewrite 停止条件                   | orchestrator           | 不无限循环                                                     |
| W4-07  | 代码 | Codex  | 确保 rewrite 不绕过 ACL/state gate      | orchestrator           | 二次检索后仍走 state gate 和 ACL gate                          |
| W4-08  | 代码 | Codex  | 实现 refusal controller                 | `refusal_controller.py` | 支持 answer、no_evidence、permission、deprecated、conflict、system_error |
| W4-09  | 代码 | Codex  | 实现 response priority                  | refusal controller     | `refuse_permission > report_conflict > warn_deprecated > answer/refuse_no_evidence` |
| W4-10  | 代码 | Codex  | 将 gates 和 rewrite 接入 orchestrator   | `orchestrator.py`      | gates 和 rewrite 真正影响 final response                       |
| W4-11  | 代码 | Codex  | 增加 trace 字段                         | trace schema           | 记录 first-pass、rewrite、second-pass、final decision          |
| W4-12  | 测试 | Codex  | 编写 ACL gate 测试                      | tests                  | 覆盖 role、clearance、blocked chunks                           |
| W4-13  | 测试 | Codex  | 编写 state gate 测试                    | tests                  | 覆盖 active、deprecated、archived、draft                       |
| W4-13b | 测试 | Codex  | 编写 conflict 检测测试                  | tests                  | active-active 触发；active-deprecated 不触发；优先级正确       |
| W4-14  | 测试 | Codex  | 编写 evidence gate 测试                 | tests                  | 覆盖 no evidence、weak evidence、multi-doc                     |
| W4-15  | 测试 | Codex  | 编写 agentic loop 测试                  | tests                  | 证据不足触发 rewrite；最多一轮；仍不足则拒答                   |
| W4-16  | 测试 | Codex  | 编写 refusal controller 测试            | tests                  | 覆盖所有决策分支                                               |
| W4-17  | 测试 | Codex  | 增加 false-positive 保护测试            | tests                  | 不能因关键词重合误答 restricted/archived 文档                  |
| W4-18  | 审查 | Claude | 审查 trust behavior                     | `TRUST_POLICY_REVIEW.md` | 检查核心场景是否符合预期                                       |
| W4-19  | 验收 | Owner  | Week 4 Scope Cut Review                 | `SCOPE_CUT_REVIEW.md`  | 按降级线收缩范围，而不是删除核心项                             |
| W4-20  | 验收 | Owner  | Week 4 验收                             | git commit             | 最小可信主链路可跑                                             |

------

## 16.2 Week 4 强制砍单检查点

Week 4 结束时必须进行 scope cut review。

### 必须保留的最小可演示路径

```text
ingest
→ real embedding retrieval
→ BM25
→ RRF
→ real reranker
→ /chat
→ citation binding
→ evidence gate
→ ACL gate
→ minimal conflict detection
→ agentic evidence recovery
→ run_eval
→ failure analysis
```

### 保护清单内部降级线

保护清单维持不可砍，但每项预设降级线。Week 4 review 时若进度落后，按降级线收缩而不是二选一删除。

| 保护项 | 满配 | 降级线 |
| ------ | ---- | ------ |
| external eval | 50 条 | 36 条（每类 n≥6，permission/deprecated 保住） |
| hard negative | 30 对 / 20 case | 20 对 / 12 case |
| obfuscated split | 15 条 | 10 条 |
| public corpus | 60–80 篇 | 40 篇 / 600 chunks |
| fixture corpus | 25 篇 | 20 篇 |
| citation 人工审计 | 40 条 | 25 条 |
| real LLM final run | external + hard_negative + obfuscated 全跑 | external 全跑 + 其余抽样 50% |
| baseline | 上述 4+3 | retrieval tier 砍 bm25_only |

不可降级的底线：

```text
grounded scoring
overlay
泄漏检查
final_gated vs final_agentic 对比
failure analysis
污染分析章节
```

### 如果进度滞后，优先砍掉

```text
/eval API
trace index
complex planner
full conflict detection
Streamlit
LangGraph wrapper
Docker optimization
complex cost tracking
advanced citation verifier
```

## 16.3 Week 4 验收命令

```bash
pytest tests/unit/test_acl_gate.py
pytest tests/unit/test_document_state_gate.py
pytest tests/unit/test_evidence_gate.py
pytest tests/unit/test_refusal_controller.py
pytest tests/unit/test_conflict_detection.py
pytest tests/integration/test_chat_api.py
python scripts/demo_queries.py
```

------

# 17. Week 5：Public Corpus + Metadata Overlay + Hard Negatives + Eval Dataset

核心目标：构建三套主 eval 与 obfuscated split 的基础数据，避免循环验证，并通过 overlay 让 external eval 覆盖 ACL/state/conflict gate。

## 17.1 Week 5 任务清单

| 编号   | 类型 | 负责人           | 任务                                      | 交付物                                  | 验收标准                                  |
| ------ | ---- | ---------------- | ----------------------------------------- | --------------------------------------- | ----------------------------------------- |
| W5-01  | 代码 | Codex            | 完善 public corpus fetch/convert          | `fetch_public_corpus.py`                | 能生成 public corpus markdown/text        |
| W5-01b | 代码 | Codex            | 实现 overlay 加载与 ingest 注入           | overlay loader / ingest                 | overlay 字段能写入 documents/chunks       |
| W5-01c | 规则 | Claude           | 起草 metadata_overlay.yaml                | `metadata_overlay.yaml`                 | restricted/confidential、deprecated 配比符合要求 |
| W5-01d | 测试 | Codex            | overlay 注入测试                          | tests                                   | seed 可复现；metadata_origin 正确         |
| W5-02  | 代码 | Codex            | 生成 public corpus manifest               | `public_corpus_manifest.yaml`           | 记录来源、路径、标题、section、tags       |
| W5-03  | 语料 | Claude           | 扩充 synthetic fixture corpus             | `data/sample_corpus/**`                 | 25 篇，仅用于 fixture eval                |
| W5-04  | 语料 | Codex + Claude   | 构造 hard negative corpus                 | `data/hard_negative_corpus/**`          | 30 对，其中 ≥20 对来自 public corpus 相邻版本 |
| W5-05  | 评测 | Claude / ChatGPT | 基于 manifest 写 fixture eval             | `fixture_eval.jsonl`                    | 36 条，不直接抄答案句                     |
| W5-05b | 评测 | Owner + Claude   | 采集真实问题并筛选改写                    | source log / eval draft                 | external eval query 来源 A ≥50%，目标 25+ 条 |
| W5-05c | 代码 | Codex            | 实现 check_eval_leakage.py                | `scripts/check_eval_leakage.py`         | 能输出 title overlap 与答案句抄写检查     |
| W5-05d | 验收 | Owner            | 泄漏检查报告归档                          | leakage report                          | 不达标 case 改写或降级                   |
| W5-06  | 评测 | Claude / ChatGPT | 编写 external eval                        | `external_eval.jsonl`                   | 50 条；含 permission/deprecated/conflict  |
| W5-07  | 评测 | Claude / ChatGPT | 编写 hard negative eval                   | `hard_negative_eval.jsonl`              | 20 条；覆盖相似标题、相似版本、相同术语不同答案 |
| W5-08  | 代码 | Codex            | 回填 gold_chunk_ids                       | eval jsonl                              | 基于实际 chunk_id 回填                    |
| W5-09  | 代码 | Codex            | 实现 eval dataset loader                  | `dataset.py`                            | 支持 fixture/external/hard_negative/obfuscated split |
| W5-10  | 代码 | Codex            | 实现 eval result 落盘格式                 | `eval_runs/{run_id}/results.jsonl`      | 每条 case 输出可追溯                      |
| W5-11  | 代码 | Codex            | 完善 trace logging                        | `tracing.py`                            | 支持 agentic loop trace                   |
| W5-12  | 代码 | Codex            | 编写 demo query 脚本                      | `demo_queries.py`                       | 一键运行核心 demo                         |
| W5-13  | 文档 | Claude           | 编写 EVAL_CASE_REVIEW                     | docs                                    | 每条 case 对应 gold doc、预期行为         |
| W5-14  | 验收 | Owner            | Week 5 验收                               | git commit                              | eval 数据可加载、可回填 gold chunks、泄漏检查归档 |

## 17.2 Week 5 验收命令

```bash
python scripts/fetch_public_corpus.py
python scripts/ingest_corpus.py --corpus all
python scripts/rebuild_indexes.py --embedding-provider sentence_transformer
python scripts/check_eval_leakage.py --all
python scripts/demo_queries.py
pytest tests/unit/test_metadata_overlay.py
pytest tests/integration/test_trace_api.py
```

------

# 18. Week 6：Baselines + Real Model Evaluation + Metrics

核心目标：使用真实 embedding、真实 reranker、真实 LLM 跑正式评测，生成分层消融表、grounded scoring、obfuscated split 对比和污染分析。

## 18.1 Week 6 任务清单

| 编号   | 类型 | 负责人 | 任务                                      | 交付物                         | 验收标准                                                     |
| ------ | ---- | ------ | ----------------------------------------- | ------------------------------ | ------------------------------------------------------------ |
| W6-01  | 代码 | Codex  | 实现 Direct LLM baseline                  | `baselines.py`                 | 不检索，直接回答                                             |
| W6-02  | 代码 | Codex  | 实现 vector_only retrieval tier           | `baselines.py`                 | real embedding + vector retrieval                            |
| W6-03  | 代码 | Codex  | 实现 bm25_only retrieval tier             | `baselines.py`                 | BM25 retrieval                                               |
| W6-04  | 代码 | Codex  | 实现 hybrid_rrf retrieval tier             | `baselines.py`                 | vector + BM25 + RRF                                          |
| W6-05  | 代码 | Codex  | 实现 hybrid_rrf_rerank retrieval tier      | `baselines.py`                 | hybrid + real reranker                                       |
| W6-06  | 代码 | Codex  | 实现 final_gated system                   | `baselines.py`                 | hybrid + rerank + gates + citation + refusal                 |
| W6-07  | 代码 | Codex  | 实现 final_agentic system                 | `baselines.py`                 | final_gated + evidence recovery                              |
| W6-08  | 代码 | Codex  | 实现 retrieval metrics                    | `metrics.py`                   | hit@1、hit@3、hit@5、MRR、gold_doc_recall@k                  |
| W6-08b | 代码 | Codex  | 实现 raw / grounded 双指标与 leakage gap  | `metrics.py`                   | raw_correctness、grounded_correctness、parametric_leakage_gap |
| W6-09  | 代码 | Codex  | 实现 hard negative metrics                | `metrics.py`                   | hard_negative_error_rate、deprecated_confusion_rate          |
| W6-10  | 代码 | Codex  | 实现 citation metrics                     | `metrics.py`                   | presence、validity、unsupported_claim_rate                   |
| W6-11  | 文档 | Claude | 设计 citation support audit 规则          | `CITATION_AUDIT_GUIDE.md`      | supported / weak / unsupported；40 条 claim 审计规则         |
| W6-12  | 代码 | Codex  | 实现 refusal metrics                      | `metrics.py`                   | refusal_accuracy、false_refusal_rate、false_answer_rate      |
| W6-13  | 代码 | Codex  | 实现 agentic recovery metrics             | `metrics.py`                   | rewrite_trigger_rate、rewrite_success_rate、second_pass_hit_improvement |
| W6-13b | 代码 | Codex  | rewrite 指标改为全量观测统计             | `metrics.py` / `report.py`     | 不再用 expected_rewrite 计分                                  |
| W6-13c | 评测 | Claude | 构造 15 条 obfuscated 变体                | `obfuscated_eval.jsonl`        | 指回 derived_from_case_id；gold 与原 case 一致                |
| W6-13d | 代码 | Codex  | obfuscated split 接入 runner              | `runner.py`                    | 输出 gated vs agentic 对比                                   |
| W6-14  | 代码 | Codex  | 实现 per-type metrics                     | `report.py`                    | n < 5 不报百分比                                             |
| W6-15  | 代码 | Codex  | 实现 eval runner                          | `runner.py`、`run_eval.py`     | 一键运行全部 baselines 和 metrics                            |
| W6-16  | 代码 | Codex  | 实现 baseline failure 导出                | `failures.jsonl`               | 可定位 naive RAG 失败案例                                    |
| W6-17  | 代码 | Codex  | 实现 summary 输出                         | `summary.json` / `summary.csv` | README / report 可引用                                       |
| W6-18  | 评测 | Owner  | 运行 real model final eval                | eval_runs                      | 至少一次 real embedding + real reranker + real LLM           |
| W6-19  | 文档 | Claude | 审查 EVALUATION_REPORT 初版               | docs                           | 检查指标解释和局限                                           |
| W6-19b | 文档 | Claude | EVALUATION_REPORT 增加污染分析章节模板    | docs                           | 包含 fixture vs external raw 差异与 leakage gap              |
| W6-20  | 验收 | Owner  | Week 6 验收                               | git commit                     | `run_eval.py` 成功，真实结果落盘                             |

## 18.2 Week 6 验收命令

```bash
python scripts/check_eval_leakage.py --all
python scripts/run_eval.py --split fixture --systems final_agentic
python scripts/run_eval.py --split external --systems vector_only,bm25_only,hybrid_rrf,hybrid_rrf_rerank --retrieval-only
python scripts/run_eval.py --split external --systems direct_llm,final_gated,final_agentic --real-run
python scripts/run_eval.py --split hard_negative --systems hybrid_rrf_rerank,final_agentic --real-run
python scripts/run_eval.py --split obfuscated --systems final_gated,final_agentic --real-run
pytest tests/evals/test_eval_metrics.py
pytest
```

------

# 19. Week 7：Engineering Delivery + Reproducible Experiment

核心目标：从“功能丰富”转向“实验可复现”。

## 19.1 Week 7 任务清单

| 编号  | 类型 | 负责人 | 任务                         | 交付物               | 验收标准                           |
| ----- | ---- | ------ | ---------------------------- | -------------------- | ---------------------------------- |
| W7-01 | 代码 | Codex  | 完善 Dockerfile              | `Dockerfile`         | API 镜像可构建                     |
| W7-02 | 代码 | Codex  | 完善 docker-compose          | `docker-compose.yml` | API + Qdrant 一键启动              |
| W7-03 | 代码 | Codex  | 编写 Makefile                | `Makefile`           | dev、ingest、test、eval、build     |
| W7-04 | 代码 | Codex  | 实现 health check API        | `health.py`          | 检查 API 和 Qdrant 状态            |
| W7-05 | 代码 | Codex  | 完善 `.env.example` 注释     | `.env.example`       | 明确 mock/real 配置                |
| W7-06 | 代码 | Codex  | 编写 smoke test              | `smoke_test.py`      | 一键验证 ingest、chat、trace、eval |
| W7-07 | 代码 | Codex  | 完善 API_SPEC                | `API_SPEC.md`        | 与 Swagger 一致                    |
| W7-08 | 测试 | Codex  | 完善集成测试                 | tests                | ingest、chat、eval、trace 全覆盖   |
| W7-09 | 文档 | Claude | 完善 README 草稿             | README draft         | 强调 eval protocol 和 real run     |
| W7-10 | 文档 | Claude | 编写 DEMO_SCRIPT             | docs                 | 覆盖 demo query 和 eval demo       |
| W7-11 | 文档 | Claude | 准备 sample responses        | README 示例响应      | 不跑项目也能看懂效果               |
| W7-12 | 代码 | Codex  | 创建 LICENSE                 | LICENSE              | GitHub 项目完整                    |
| W7-13 | 代码 | Codex  | 把文档草稿落入 repo 并修链接 | README、docs         | Markdown 链接正确                  |
| W7-14 | 验收 | Owner  | Week 7 验收                  | git commit           | 新环境可按 README 复现             |

## 19.2 Week 7 验收命令

```bash
docker compose up --build
python scripts/smoke_test.py
make test
make eval
```

------

# 20. Week 8：Evaluation Report + Failure Analysis + Interview Packaging

核心目标：完成真正能拿出去讲的材料。

## 20.1 Week 8 任务清单

| 编号  | 类型 | 负责人 | 任务                           | 交付物                      | 验收标准                                                    |
| ----- | ---- | ------ | ------------------------------ | --------------------------- | ----------------------------------------------------------- |
| W8-01 | 文档 | Claude | 完成 TECHNICAL_DESIGN 初稿     | `TECHNICAL_DESIGN.md`       | 问题定义、目标、非目标、架构、workflow、API、失败处理、取舍 |
| W8-02 | 文档 | Claude | 完成 EVALUATION_REPORT 完整版  | `EVALUATION_REPORT.md`      | 使用真实结果，区分 fixture/external/hard_negative           |
| W8-03 | 文档 | Claude | 完成 FAILURE_ANALYSIS          | `FAILURE_ANALYSIS.md`       | 覆盖 failure taxonomy                                       |
| W8-04 | 文档 | Claude | 完成 CITATION_AUDIT            | `CITATION_AUDIT.md`         | 人工抽样 citation support 结果                              |
| W8-05 | 文档 | Claude | 完成 PROJECT_REVIEW            | `PROJECT_REVIEW.md`         | 讲清设计取舍、失败、后续计划                                |
| W8-06 | 文档 | Claude | 完成 INTERVIEW_QA              | `INTERVIEW_QA.md`           | 覆盖 RAG、Agent、eval、citation、refusal、ACL、state gate   |
| W8-07 | 文档 | Claude | 完成 DEMO_VIDEO_SCRIPT         | `DEMO_VIDEO_SCRIPT.md`      | 3–5 分钟录屏可照着讲                                        |
| W8-08 | 文档 | Claude | 编写简历要点                   | `RESUME_BULLETS.md`         | 不预设虚假数字，使用真实 eval 结果                          |
| W8-09 | 文档 | Claude | 编写 ROADMAP                   | `ROADMAP.md`                | Q2/Q3 计划                                                  |
| W8-10 | 代码 | Codex  | 完善 README 最终版             | README                      | 架构图、demo、结果、项目结构、快速启动                      |
| W8-11 | 代码 | Codex  | 将所有文档落入 repo 并修正链接 | docs、README                | Markdown 链接正确                                           |
| W8-12 | 审查 | Claude | 最终文档审查                   | `FINAL_DOC_REVIEW.md`       | 检查术语统一、结果真实、面试可讲                            |
| W8-13 | 验收 | Owner  | 最终代码冻结                   | Git tag `v0.2-q1-hard-demo` | GitHub release 可展示                                       |
| W8-14 | 验收 | Owner  | 最终项目验收                   | release notes               | README、demo、eval、trace、Docker 全部可用                  |

## 20.2 Week 8 最终验收命令

```bash
make test
make ingest
make eval
make smoke
docker compose up --build
```

------

# 21. 最终 Demo Query 固定清单

Q1 最终 demo 至少包含以下问题。

| 类型                  | 示例问题                                             | 展示点                                |
| --------------------- | ---------------------------------------------------- | ------------------------------------- |
| 单文档事实问答        | Auth Service v2 的 refresh token rate limit 是多少？ | citation                              |
| 多文档综合问答        | 上线前需要满足哪些测试和部署要求？                   | multi-doc synthesis                   |
| 文档过期问题          | 旧版 token 限流规则现在还有效吗？                    | document state gate                   |
| 权限外问题            | 管理员密钥轮换 SOP 是什么？                          | ACL gate + refusal                    |
| 无证据问题            | CEO 上周在客户会上承诺了什么？                       | evidence gate + refusal               |
| 冲突问题              | OAuth token 有效期到底是 30 分钟还是 60 分钟？       | conflict detection                    |
| Agentic recovery 问题 | 用缩写或非标准说法询问一个存在但首轮检索弱的问题     | query rewrite + second-pass retrieval |
| Hard negative 问题    | 两个相似版本中哪个规则当前有效？                     | hard negative robustness              |

------

# 22. Eval Case Schema 要求

每条 eval case 至少包含：

```json
{
  "case_id": "EVAL-001",
  "query": "Auth Service v2 的 refresh token rate limit 是多少？",
  "query_type": "single_doc_fact",
  "eval_split": "external",
  "corpus_source": "public_external",
  "query_source": "real_user_question",
  "query_source_url": "https://example.com/source-thread-or-issue",
  "title_overlap_score": 0.22,
  "query_style": "standard",
  "derived_from_case_id": null,
  "user_role": "engineer",
  "user_department": "engineering",
  "user_clearance": "internal",
  "expected_behavior": "answer",
  "gold_doc_ids": ["DOC-API-AUTH-V2"],
  "gold_chunk_ids": ["CHK-API-AUTH-V2-0007"],
  "reference_answer": "Refresh token 接口每分钟限制 30 次。",
  "must_cite": true,
  "must_refuse": false,
  "requires_real_model": true,
  "expected_rewrite": null,
  "hard_negative_group_id": null
}
```

字段要求：

| 字段 | 要求 |
| ---- | ---- |
| `query_source` | `real_user_question` 或 `manifest_authored` |
| `query_source_url` | 真实问题来源链接；manifest 出题可为 null |
| `title_overlap_score` | 由 `check_eval_leakage.py` 回填 |
| `query_style` | `standard` 或 `obfuscated` |
| `derived_from_case_id` | obfuscated case 指回原 case；普通 case 为 null |
| `expected_rewrite` | 仅作为 informational 注释字段，不参与计分 |

Week 0 可以暂时缺 `gold_chunk_ids`，但 Week 1 后必须回填。
Week 5 eval 数据冻结前必须运行 `check_eval_leakage.py` 并归档报告。

------

# 23. Commit 规范

建议使用以下 commit 前缀：

| 前缀          | 含义                              |
| ------------- | --------------------------------- |
| `init:`       | 初始化                            |
| `schema:`     | schema 修改                       |
| `ingest:`     | 文档导入与解析                    |
| `corpus:`     | 语料                              |
| `index:`      | 索引构建                          |
| `retrieval:`  | 检索模块                          |
| `rerank:`     | 重排                              |
| `agentic:`    | query rewrite / evidence recovery |
| `generation:` | 生成与引用                        |
| `guard:`      | state / ACL / evidence / refusal  |
| `trace:`      | trace 与 observability            |
| `eval:`       | 评测                              |
| `api:`        | API                               |
| `test:`       | 测试                              |
| `docs:`       | 文档                              |
| `docker:`     | Docker                            |
| `release:`    | 版本冻结                          |

示例：

```bash
git commit -m "init: set up q1 hard demo foundation"
git commit -m "ingest: add markdown parser and section-aware chunker"
git commit -m "retrieval: implement sentence-transformer and hybrid search"
git commit -m "rerank: add bge reranker for formal ablation"
git commit -m "agentic: add evidence recovery loop"
git commit -m "eval: add external corpus baselines and trust metrics"
```

------

# 24. 每周 Gate

## Gate 0：项目可启动

必须满足：

- FastAPI 可启动；
- Swagger 可访问；
- schema 测试通过；
- mock-first 配置可用；
- 配置中明确 mock 不用于正式 eval。

## Gate 1：文档可结构化

必须满足：

- synthetic 文档可解析；
- chunks 可生成；
- chunk metadata 完整；
- corpus_source 可追踪；
- gold_chunk_ids 可回填。

## Gate 2：真实检索可用

必须满足：

- sentence-transformer embedding 可用；
- Qdrant 可检索；
- Whoosh 可检索；
- RRF 可融合；
- search preview 可展示 top-k。

## Gate 3：问答可引用

必须满足：

- BGE reranker 可用；
- `/chat` 可返回 answer；
- citations 来自 ContextPack；
- MockLLM 可测试；
- real LLM 接口可 dry run；
- fake citation 被拦截。

## Gate 4：可信控制与 Agentic Recovery 可用

必须满足：

- 无证据触发 rewrite；
- 最多二次检索一轮；
- 仍不足则拒答；
- 权限拒答；
- deprecated warning；
- gates 和 rewrite 写入 trace；
- 完成 scope cut review。

## Gate 5：评测数据与泄漏检查可用

必须满足：

- fixture eval 可用；
- external eval 可用；
- hard negative eval 可用；
- 每条有 expected_behavior；
- gold_doc_ids 完整；
- gold_chunk_ids 回填；
- eval author isolation 有记录。

## Gate 6：真实模型评测与 grounded scoring 可用

必须满足：

- real embedding；
- real reranker；
- real LLM final run；
- baseline ablation；
- citation metrics；
- refusal metrics；
- agentic recovery metrics；
- failure export。

## Gate 7：工程可复现

必须满足：

- Docker 可启动；
- Makefile 可用；
- smoke test 可用；
- README quickstart 可复现。

## Gate 8：项目可展示

必须满足：

- README 完整；
- TECHNICAL_DESIGN 完整；
- EVALUATION_REPORT 使用真实结果；
- FAILURE_ANALYSIS 完整；
- CITATION_AUDIT 完整；
- DEMO_SCRIPT 可执行；
- tag `v0.2-q1-hard-demo`。

------

# 25. 核心风险与规避

| 风险                         | 表现                                 | 规避                                                 |
| ---------------------------- | ------------------------------------ | ---------------------------------------------------- |
| 自产语料循环验证             | eval 和语料共谋                      | 加 public external corpus；eval author 只看 manifest |
| Mock 数字无效                | hash embedding / mock LLM 得出假指标 | mock 只用于测试；正式评测必须 real run               |
| MockReranker 无意义          | 不能讲 rerank 消融                   | BGE reranker 进入 P0                                 |
| 小语料 baseline 不显著       | BM25 接近饱和，hybrid 提升不明显     | public corpus + hard negatives                       |
| Agent 超卖                   | 固定 pipeline 被问住                 | 加 evidence recovery loop                            |
| Week 6–8 被压缩              | 最有价值的评测和失败分析没做完       | Week 4 强制砍 P1，保 eval                            |
| ask_clarification 没模块负责 | response mode 不一致                 | Q1 删除该 mode                                       |
| prompt 与 parser 脱节        | Claude prompt 与 Codex parser 不匹配 | Codex 统一负责 prompt + parser                       |
| citation 做成假引用          | 只是答案末尾附来源                   | claim 绑定 chunk_id，人工抽样 support audit          |
| false refusal 过高           | 系统过保守                           | 报告 false refusal vs false answer trade-off         |
| real LLM 成本不可控          | Week 6 跑不完                        | 控制 eval 样本，至少跑一轮 final real run            |
| Docker 消耗时间              | 工程交付拖累评测                     | Docker 优化降级，能启动即可                          |

------

# 26. Q1 最终交付物清单

Q1 完成后，repo 中必须存在：

```text
1. 可运行 FastAPI 服务
2. 可导入的 synthetic fixture corpus
3. 可导入的 public external corpus
4. 可导入的 hard negative corpus
5. corpus manifests
6. documents.jsonl
7. chunks.jsonl
8. Qdrant vector index
9. Whoosh BM25 index
10. sentence-transformer embedding provider
11. BGE reranker provider
12. real LLM client
13. /chat API
14. /ingest API
15. /documents API
16. /traces API
17. citation/refusal/state/ACL/agentic recovery 可见的 response
18. trace JSONL
19. fixture_eval.jsonl
20. external_eval.jsonl
21. hard_negative_eval.jsonl
22. direct LLM baseline
23. vector only baseline
24. BM25 only baseline
25. hybrid RRF baseline
26. hybrid RRF + rerank baseline
27. final gated system
28. final agentic system
29. metrics summary
30. failures.jsonl
31. citation audit result
32. EVALUATION_REPORT.md
33. FAILURE_ANALYSIS.md
34. CITATION_AUDIT.md
35. TECHNICAL_DESIGN.md
36. API_SPEC.md
37. DEMO_SCRIPT.md
38. INTERVIEW_QA.md
39. README.md
40. Dockerfile
41. docker-compose.yml
42. Makefile
43. smoke_test.py
44. v0.3-q1-hard-demo-plan-freeze
```

------

# 27. 简历材料输出原则

简历 bullet 不得提前写虚假数字。
只有在 `scripts/run_eval.py` 跑出真实结果后，才能写：

- hit@k；
- MRR；
- citation support accuracy；
- refusal accuracy；
- false refusal；
- false answer；
- agentic recovery success rate；
- latency；
- baseline improvement。

无数字版本：

```text
设计并实现面向企业文档的可信 RAG-Agent 问答系统，覆盖 Markdown/TXT 文档导入、section-aware chunking、真实 embedding 检索、BM25、RRF 混合检索、BGE rerank、agentic evidence recovery、上下文组装、引用绑定、文档状态/权限门控、拒答控制、trace logging、自动化评测与 FastAPI 部署。
```

有真实评测结果后再升级为：

```text
构建可信企业文档 RAG-Agent QA 系统，在 public external corpus 与 hard negative eval 上对比 direct LLM、vector-only RAG、BM25、hybrid RRF、hybrid+rerank 与 final agentic system，使用 retrieval hit@k、MRR、citation support audit、refusal accuracy、false refusal / false answer trade-off 等指标验证系统相对 naive RAG 的可信性改进。
```

------

# 28. Q2 Roadmap 草案

Q1 完成后，Q2 再考虑：

| 优先级 | 方向                        |
| ------ | --------------------------- |
| Q2-P0  | PDF / 表格解析              |
| Q2-P0  | 更强 public corpus 自动采集 |
| Q2-P0  | 更强 citation verification  |
| Q2-P1  | LangGraph workflow wrapper  |
| Q2-P1  | Phoenix / OpenInference     |
| Q2-P1  | Streamlit demo UI           |
| Q2-P2  | Elasticsearch               |
| Q2-P2  | 增量索引                    |
| Q2-P2  | 多角色权限配置面板          |
| Q2-P3  | React 前端                  |
| Q2-P3  | 云部署                      |
| Q2-P3  | 多租户                      |
| Q2-P3  | human-in-the-loop review    |

------

# 29. 最终执行原则

1. 先做可运行主链，不追大而全。
2. Mock 只用于测试，不用于正式评测数字。
3. 正式评测必须使用 real embedding、real reranker、real LLM。
4. 自产语料只做 fixture，不做 headline metrics。
5. public external corpus 是外部效度核心。
6. hard negatives 是检索鲁棒性核心。
7. eval author 与 corpus author 流程隔离。
8. rerank 消融必须基于真实 reranker。
9. Agent 名称必须由 evidence recovery loop 支撑。
10. Week 4 必须按降级线收缩范围，保 eval 和 failure analysis。
11. 删除 ask_clarification，避免无模块负责。
12. prompt 与 parser 由 Codex 统一落地。
13. 所有简历数字必须来自真实 eval run，headline 只引用 grounded_correctness。
14. 最终叙事必须讲“如何证明更可信，以及仍然在哪里失败”。
15. external corpus 可能有训练数据污染，必须用 grounded scoring 和 leakage gap 显式隔离。
16. public corpus 文本真实，ACL/state/conflict 可通过 metadata overlay 受控叠加。
17. Agentic 名称的量化依据是 obfuscated split 上 final_gated vs final_agentic 的差异。
18. 修改完成后冻结为 `v0.3-q1-hard-demo-plan-freeze`，此后计划只走 Week 4 降级线，不再增项。
15. headline 指标改用 grounded_correctness，显式隔离 public corpus 训练数据污染。
16. public corpus 文本保持真实公开来源，ACL/state/conflict 通过 metadata overlay 受控叠加。
17. external eval query 至少 50% 来自真实人类问题，并通过自动泄漏检查。
18. baseline 分层为 retrieval tier 与 end-to-end tier，避免端到端 LLM 调用量超载。
19. Agentic loop 的价值用 obfuscated split 单独量化。