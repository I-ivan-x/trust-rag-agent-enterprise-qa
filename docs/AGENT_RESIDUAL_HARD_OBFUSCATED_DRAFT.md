# Hard-Obfuscated 补充草稿（AR-H01..H08，Claude 出题，for P3-09 §1d）

> 目的：把 weak_recall/action-a 触发数从 3 → ≥8，让"LLM vs 规则改写质量"的对比床够。
> **复用现有 Northstar agent_residual gold 文档，无需新语料**——只加 eval case。
> Codex 加入 agent_residual_eval（scenario_type=weak_recall_hard）+ annotations，重跑 §1d 预检。

## 设计依据（从预检实证学到的）

触发 weak_recall 需要 entity_miss=true + evidence insufficient。实测：
- **会触发**：电报式 + 内部缩写/黑话 + 回避 gold 关键术语（AR-001 "auth token ttl"、
  AR-002 "rlimit"）。
- **不会触发**：完整口语句含强实体词（"CORS"、"422"）→ bge 语义直接命中 gold。

所以下面的 query 一律：**电报式（省冠词/动词）+ 常见可展开缩写 + 不出现 gold 的标志词**。
缩写选"规则改写器也能展开"的常见类（pwd/ttl/svc/creds），保证两改写器公平，
**不调到只有 LLM 能解。**

## 8 条（gold 复用现有 active 文档）

| case | gold 文档（复用） | gold 关键答案 | query（电报式+黑话，回避标志词） |
| --- | --- | --- | --- |
| AR-H01 | nc-deploy-checklist-2026 | green CI / soak≥30min / on-call ack / rollback owner | `prod ship gates? whats gotta pass b4 we cut a release` |
| AR-H02 | nc-retention-2026 | request logs 留 90 天后清除 | `req log ttl b4 we purge em?` |
| AR-H03 | nc-webhook-retry-2026 | 指数退避最多 24h 后丢弃 | `hook delivery flaky when endpoint down — retry window?` |
| AR-H04 | nc-password-policy-2026 | ≥12 字符 + 大小写 + 数字 | `pwd strength reqs? min len n complexity` |
| AR-H05 | nc-healthcheck | GET /healthz 返回 200 | `svc liveness probe path?` |
| AR-H06 | nc-config-env | 环境变量 NORTHSTAR_API_KEY | `where stash creds for api auth — which env var?` |
| AR-H07 | nc-sso-oidc | OIDC：注册 client / redirect URI / 映射 email claim | `unified login across apps — idp wireup steps?` |
| AR-H08 | nc-pagination-cursor-v2 | cursor 参数 + next_cursor 直到 null | `walk thru a big resultset page by page — which knob?` |

说明：
- 标志词回避示例：AR-H05 用 "svc liveness probe"（k8s 黑话）而非 gold 的 "/healthz"；
  AR-H02 用 "ttl/purge" 而非 "retention"；AR-H07 用 "idp/unified login" 而非 "SSO/OIDC"。
- 这些是真实内部用户会打的电报式 query（带行话），不是人为刁难。
- gold 答案不变；query 不抄答案句（过 answer-copy）；含区分性内容词（过 no_retrievable_content 下限）。

## Codex 落地 + 重跑 §1d

```text
1. 加 8 条到 agent_residual_eval.jsonl（gold_doc_ids 指向上表现有文档；gold_chunk_ids 回填）。
2. annotations 加 8 行（scenario_type=weak_recall_hard，expected_failure_type=WEAK_RECALL，
   expected_legal_actions=[rewrite_query, refuse_with_explanation]）。注：annotation 是预期，
   真实 diagnose 以预检为准。
3. 双向泄漏检查这 8 条。
4. 重跑 §1d 零 token 预检，统计 weak_recall 触发总数。
```

## 诚实兜底（重要）

- 这批是**合理批量**，不是"加到正好 8 为止"。重跑后：
  - 触发总数 ≥8 → 改写对比床够,放行消融。
  - 6–7 → 够用,直接跑(报实际触发数)。
  - 仍 <6 → **那本身是结论**："bge 检索对糟糕措辞高度鲁棒,agent 改写的触发面天然狭窄",
    如实写进 P3-11,在现有触发 case 上跑小消融。**不再无限加料。**
- 任一改写器在这些 case 上恢复得好都如实报；**绝不因 llm 输就改 query。**
