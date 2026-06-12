# Hard-Negative 失败归因裁定材料（预消化稿）

> 性质：Claude 预消化稿，对应 ROADMAP C1-04。结论需 Owner 逐项裁定后才生效。
> 数据来源：`data/gold_eval/hard_negative_eval.jsonl`（20 条）、
> `data/hard_negative_corpus/hard_negative_manifest.jsonl`（20 对）、
> `week6-hard-negative-real-retrieval` 与 `week6-hard-negative-final-agentic-real` 的 traces。
> 本文不修改任何 eval 数据；建议的替换 query 仅为草稿，冻结前必须重过
> `check_eval_leakage.py` 并由 Codex 回填 gold_chunk_ids。

------

## 1. 预消化总结论（待裁定）

**F8（gold/query 设计缺陷）是全部 20 条失败的主因，且证据接近决定性；
F3（检索真实弱点）在当前数据下根本未被测试。**

这比 `FAILURE_ANALYSIS.md` 现有表述（"现有证据无法完全区分 F3 与 F8"）更进一步：
新证据显示这不是"无法区分"，而是该 split 的 query 构造方式使 F3 不可能被测到。

## 2. 证据

### 证据 1：20/20 条 query 是同一个元数据模板

全部 query 形如：

```text
In hard negative group hn-fastapi-0001, answer from side A using the relevant FastAPI guidance.
```

query 中唯一的变量是组号和侧别字母——这两者都是**索引中不可检索的元数据**，
不含任何能区分主题的内容词。对内容检索而言，20 条 query 实质上是同一句话。
`title_overlap_score=0.0` 通过泄漏检查，但那是因为 query 不含内容词——
泄漏检查防的是"内容词过多"，没有防住"内容词为零"。

### 证据 2：检索结果呈与 query 无关的均匀坍缩

对 20 条 case 的 top-5 去重文档统计（retrieval-only run）：

```text
hn-fastapi-0019 组文档：出现 40 次（= 两侧文档进入了全部 20 条 case 的 top-5）
hn-fastapi-0020 组文档：出现 20 次（= 一侧文档进入了全部 20 条 case 的 top-5）
hn-fastapi-0011 组文档：出现 20 次
```

每条 case 的 top-3 几乎完全相同：`0019-b, 0019-a, 0020-a`。
原因显而易见：模板 query 里仅有的内容词是 "FastAPI" 和 "guidance"，
而 0019 组恰好是 FastAPI 的 index 页（'FastAPI'）和 'Features' 页，
0020 组是 'Alternatives' 和 'Tutorial - User Guide'——全语料中最"泛 FastAPI"的页面。
检索行为完全正确地反映了 query 内容；坍缩不是检索混淆，是 query 无信息。

### 证据 3：仅有的 2 次 "gold hit" 是坍缩砸中自己组的巧合

- `hard-negative-019`：gold 是 `0019-a`（FastAPI index 页本身）——万能 top-3 必然包含它；
- `hard-negative-006`：gold（`0006-b`）出现在坍缩 top-5 的尾部，同属巧合性命中。

doc_hit@5 = 0.05（=2/40 侧次）的全部来源即此。final_agentic run 的坍缩模式与
retrieval-only run 完全一致，agentic 路径无机会改变结果（与 F5 结论一致）。

## 3. 对现有文档与计划的影响（待裁定后执行）

1. **FAILURE_ANALYSIS.md**：F8 从"风险"升级为"已证实的主因"；F3 改为"未被测试"；
   "Hard-Negative Failure Analysis" 节的双假设表述按本文证据收紧。
   mitigation 排序必须修改：**"stronger reranker" 从第一位移除**——
   query 无内容词时，任何 reranker 都无济于事；第一位改为"重写 query 后复测"。
2. **EVALUATION_REPORT.md**：`hard_negative_error_rate=1.0` 作为 failure finding 的
   定性不变（依然不可声称鲁棒性），但失败性质重新归因：
   从"检索压力测试失败"改为"该 split 的压力测试因 query 设计缺陷而无效，
   检索鲁棒性结论待重写 query 后产出"。
3. **ROADMAP**：P3 动作 c（version-scoped retrieval，攻 F3）的前提被削弱——
   F3 是否存在要等重写 query 复测后才知道。复测本身是 **retrieval-only、零 LLM 成本**，
   可以在 Q1 收尾或 Q2-W1 顺手完成（重过泄漏检查 + 回填 gold + 重跑
   `week?-hard-negative-rewritten-retrieval`）。
4. **EVAL_PROTOCOL 修订建议**：泄漏检查增加下限规则——
   query 内容词与 gold 文档主题的重合不得为零（防"元数据模板题"）；
   并为 hard_negative split 增加例外说明：similar_title 对的区分词本身就是标题词，
   title_overlap 偏高是该 split 的固有属性，应单独计量而非一律降级。

## 4. 逐对裁定表

说明：verdict 为我的预判；replacement query 为草稿（真实用户风格、含区分性内容词、
不抄 reference answer 原句）。Owner 在最后一列裁定：同意 / 修改 / 弃用该 case。

| case | 组 | 类型 | gold 侧 | gold 标题 vs 对侧标题 | 预判 | 替换 query 草稿 | Owner 裁定 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 001 | 0001 | similar_title | A | Declare Request Example Data vs Extra Data Types | F8 | How can I show example payloads for my request body in the generated API docs? | |
| 002 | 0002 | similar_title | B | Header Parameters vs Cookie Parameters | F8 | How do I read a custom HTTP header value inside my endpoint function? | |
| 003 | 0003 | adjacent_topic | A | Response Model - Return Type vs Extra Models | F8 | Can I control the response schema just by annotating the return type of my path function? | |
| 004 | 0004 | adjacent_topic | B | Form Data vs Response Status Code | F8 | My endpoint receives an HTML form POST instead of JSON — how do I declare those fields? | |
| 005 | 0005 | similar_title | A | Request Files vs Request Forms and Files | F8 | How do I declare a parameter for a single uploaded file in an endpoint? | |
| 006 | 0006 | adjacent_topic | B | Path Operation Configuration vs Handling Errors | F8（命中系巧合） | What options can I pass to the route decorator to set tags, summary, or response status code? | |
| 007 | 0007 | adjacent_topic | A | JSON Compatible Encoder vs Body - Updates | F8 | How do I convert a Pydantic model into a JSON-safe dict before storing it in a database? | |
| 008 | 0008 | similar_title | B | Classes as Dependencies vs Dependencies | F8 | Can I use a class instead of a function as a dependency, and what do I get from that? | |
| 009 | 0009 | similar_title | A | Sub-dependencies vs Dependencies in path operation decorators | F8 | Can a dependency itself depend on another dependency? How does the chain get resolved? | |
| 010 | 0010 | similar_title | B | Dependencies with yield vs Global Dependencies | F8 | How do I run cleanup code after a request finishes, like closing a database session opened by a dependency? | |
| 011 | 0011 | similar_title | A | Security vs Security - First Steps | F8；对侧高度相近，重写后仍是真正的难例 | Which auth standards (OAuth2, OpenID Connect, API keys) do the built-in security utilities cover? | |
| 012 | 0012 | adjacent_topic | B | Simple OAuth2 with Password and Bearer vs Get Current User | F8 | What is the simplest way to wire up a username/password login that returns a bearer token? | |
| 013 | 0013 | adjacent_topic | A | OAuth2 with Password (and hashing), Bearer with JWT tokens vs Middleware | F8 | How do I issue and verify JWT access tokens with hashed passwords for login? | |
| 014 | 0014 | adjacent_topic | B | First Steps vs CORS | F8 | What does the minimal hello-world app file look like and how do I run it? | |
| 015 | 0015 | similar_title | A | Path Parameters vs Query Parameters | F8；重写后是优质难例 | How do I capture a variable segment of the URL path as a typed function argument? | |
| 016 | 0016 | adjacent_topic | B | Query Parameters and String Validations vs Request Body | F8 | How do I add a max length or regex validation to a query parameter? | |
| 017 | 0017 | similar_title | A | Path Parameters and Numeric Validations vs Body - Multiple Parameters | F8 | How do I enforce numeric constraints like greater-than-or-equal on a path parameter? | |
| 018 | 0018 | similar_title | B | Body - Nested Models vs Body - Fields | F8 | How do I define a request body model that contains a list of other models nested inside it? | |
| 019 | 0019 | adjacent_topic | A | FastAPI（index 页）vs Features | F8 + **gold 质量缺陷**：gold chunk-0000 为 HTML/样式样板文本 | （建议弃用或重锚 gold 至实质内容 chunk） | |
| 020 | 0020 | adjacent_topic | B | Tutorial - User Guide vs Alternatives | F8 + gold 偏元描述（教程组织方式） | （建议弃用或降级为 case study） | |

## 5. 裁定后的执行清单（零 token，代码改动≈0）

```text
1. Owner 在 §4 表格逐行裁定（预计 ≤30 分钟）。
2. Claude 按裁定定稿 18 条替换 query（019/020 弃用或重锚）。
3. Codex：重过 check_eval_leakage.py（注意 §3.4 的 hard_negative 例外说明）、
   回填 gold_chunk_ids、重跑 retrieval-only run（零 LLM 调用）。
4. 新结果写入 FAILURE_ANALYSIS / EVALUATION_REPORT 修订（§3.1、§3.2）。
5. 重写后若 doc_hit@5 仍显著低 → F3 成立，Q2 P3 动作 c 的前提恢复；
   若恢复正常 → F3 不成立，Q2 动作空间据此收缩，省下的量能给 A/B/C。
6. 019/020 弃用后 split 收缩为 18 条；此后所有报告一律标 n=18，不再写 20。
7. 重写 split 的 final_agentic **real run**（≈20 次调用）排 Q2-W1：
   一是恢复 hard-negative 的端到端语义，二是为 citation 审计补 hard_negative 层
   （`CITATION_AUDIT_GUIDE.md` §3 的 deferred stratum）。
```

## 6. 方法论备注

本次预消化本身是评测体系的一次自检成功案例：泄漏检查防住了"query 抄答案"，
但没防住"query 无内容"——两个方向的失效模式只堵了一个。
这条教训值得写进 TECHNICAL_DESIGN 的 evaluation governance ADR：
**出题协议需要双向边界（信息过多 = 泄漏；信息为零 = 不可检索），
且任何 split 冻结前应抽样人读 query 本身，而不只是跑自动检查。**
