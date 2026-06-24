# Agent Residual `agent_residual_v1` — 10 条草稿（Claude 出题）

> 配合 `SPEC_P3_08_RESIDUAL_TESTBED.md`。Codex 据此落 `data/agent_residual_corpus/`
> 文档 + `agent_residual_eval.jsonl` + 旁路 annotations，跑验证 gate（diagnose 逐条符预期、
> 共现 ≥6、gold 可达）+ 双向泄漏检查 + gold 回填。
> 语料风格：Northstar Cloud 企业内部文档（贴合现有 fixture）。corpus_source=agent_residual。

## 设计原则（信号怎么被可靠触发）

- **weak_recall**：query 用缩写/口语，gold 的正式术语不被直接命中（entity_miss）。
- **policy_crowding**：同 topic 放 2 个 deprecated/restricted 邻居，挤占 1 个 active gold。
- **共现**：上面两者同时 → legal={a,b,e}（控制器决策点）。
- 每个 gold 设计为单一主 chunk，clean_active 保持低位，对占位阈值留余量。

------

## 共现 case（6 条，legal={a,b,e}，scenario=cooccurrence）

### AR-001 token 限流
- 文档：
  - `gold` **nc-ratelimit-v3**（active）：「Token refresh endpoint is limited to **60 requests per minute** per client in API v3.」
  - sibling **nc-ratelimit-v1**（deprecated）：v1 限 30/min
  - sibling **nc-ratelimit-v2**（deprecated）：v2 限 45/min
- query（缩写口语）：`whats the cap on token refreshes these days?`
- gold 答案：60 requests/min（v3）
- expected：failure_type=policy_crowding，legal={a,b,e}，behavior=answer

### AR-002 上线前置
- 文档：
  - `gold` **nc-deploy-checklist-2026**（active）：「Before production deploy: green CI, staging soak ≥ 30 min, on-call ack, rollback owner named.」
  - sibling **nc-deploy-old**（deprecated）：旧三步清单
  - sibling **nc-hotfix-sop**（restricted, access=admin）：紧急热修流程
- query：`what do i need to tick off before pushing to prod?`
- gold 答案：green CI / staging soak ≥30min / on-call ack / rollback owner
- expected：policy_crowding，{a,b,e}，answer

### AR-003 单点登录配置
- 文档：
  - `gold` **nc-sso-oidc**（active）：「Configure SSO via OIDC: register the client, set redirect URI, map the `email` claim to user identity.」
  - sibling **nc-sso-saml-legacy**（deprecated）：旧 SAML 配置
  - sibling **nc-sso-admin-override**（restricted, access=admin）：管理员强制 SSO 覆盖
- query：`how do i wire up single sign-on for my app?`
- gold 答案：OIDC（注册 client、redirect URI、映射 email claim）
- expected：policy_crowding，{a,b,e}，answer

### AR-004 日志留存
- 文档：
  - `gold` **nc-retention-2026**（active）：「Customer request logs are retained for **90 days**, then purged.」
  - sibling **nc-retention-old**（deprecated）：旧 30 天
  - sibling **nc-legalhold-sop**（restricted, access=legal）：法务保全 SOP
- query：`how long do we hang on to customer logs?`
- gold 答案：90 天
- expected：policy_crowding，{a,b,e}，answer

### AR-005 分页
- 文档：
  - `gold` **nc-pagination-cursor-v2**（active）：「Paginate with the `cursor` parameter; follow `next_cursor` until null.」
  - sibling **nc-pagination-cursor-v1**（deprecated）：cursor v1
  - sibling **nc-pagination-offset**（deprecated）：offset 分页
- query：`how do i page thru a big result set?`
- gold 答案：cursor 参数 + next_cursor 直到 null
- expected：policy_crowding，{a,b,e}，answer

### AR-006 webhook 重试
- 文档：
  - `gold` **nc-webhook-retry-2026**（active）：「Failed webhook deliveries retry with exponential backoff for up to **24 hours**, then drop.」
  - sibling **nc-webhook-backoff-old**（deprecated）：旧固定间隔重试
  - sibling **nc-queue-ops**（restricted, access=admin）：内部队列运维
- query：`what happens if my webhook url is down for a bit?`
- gold 答案：指数退避重试最多 24 小时后丢弃
- expected：policy_crowding，{a,b,e}，answer

------

## 纯 weak_recall（2 条，legal={a,e}，scenario=weak_recall）

> 干净 topic，无 deprecated/restricted 邻居；仅缩写 query 触发 weak_recall。

### AR-007 健康检查
- 文档：`gold` **nc-healthcheck**（active）：「`GET /healthz` returns 200 when the service is ready.」（无 sibling）
- query：`how do i tell if the service is up?`
- gold 答案：GET /healthz 返回 200
- expected：failure_type=weak_recall，legal={a,e}，behavior=answer

### AR-008 环境变量
- 文档：`gold` **nc-config-env**（active）：「Set the API key via the `NORTHSTAR_API_KEY` environment variable.」（无 sibling）
- query：`where do i drop in my api key?`
- gold 答案：环境变量 NORTHSTAR_API_KEY
- expected：weak_recall，{a,e}，answer

------

## 纯 policy_crowding（1 条，legal={b,e}，scenario=policy_crowding）

> query 清晰具体（不缩写，weak_recall 不触发），但被 deprecated/restricted 邻居挤占。

### AR-009 密码策略
- 文档：
  - `gold` **nc-password-policy-2026**（active）：「Passwords must be at least 12 characters and include upper, lower, and a digit.」
  - sibling **nc-password-old**（deprecated）：旧 8 字符策略
  - sibling **nc-admin-reset-sop**（restricted, access=admin）：管理员重置 SOP
- query（清晰、含正式术语，避免 entity_miss）：`What are the current minimum password length and complexity requirements?`
- gold 答案：≥12 字符 + 大小写 + 数字
- expected：failure_type=policy_crowding，legal={b,e}，behavior=answer

------

## 冲突兜底（1 条，legal={d,e}，scenario=conflict）

### AR-010 会话超时（active-active 冲突）
- 文档（同 conflict_group_id=`nc-session-timeout`，两者皆 active）：
  - **nc-session-web**（active）：「Web sessions expire after **30 minutes** of inactivity.」
  - **nc-session-api**（active）：「API sessions expire after **60 minutes** of inactivity.」
- query：`how long till my session times out?`
- gold：两文档 doc_id（冲突呈现，不给唯一值）
- expected：failure_type=conflict（active-active 同组），legal={d,e}，behavior=report_conflict

------

## 标注汇总（落 `agent_residual_v1_annotations.jsonl`，非评分）

| case | scenario_type | expected_failure_type | expected_legal_actions |
| --- | --- | --- | --- |
| AR-001..006 | cooccurrence | policy_crowding | a,b,e |
| AR-007,008 | weak_recall | weak_recall | a,e |
| AR-009 | policy_crowding | policy_crowding | b,e |
| AR-010 | conflict | conflict | d,e |

共现 6 条 ≥ 硬指标 6。

## 给 Codex 的落地注意

- 文档正文可按上面「key 内容」扩成 2–4 句正常 markdown（含 front matter:
  status/access_level/version/conflict_group_id）。gold 主 chunk 含 key 答案句。
- query **不得**抄 gold 答案句（过 answer-copy 检查）；但含区分性内容词（过 no_retrievable_content 下限）。
- 验证 gate 跑 diagnose() 若某条 legal_actions 不符（占位阈值脆性）→ 调邻居数/query 弱化程度，
  或在 PR 标注阈值依赖；共现必须凑满 ≥6。
- gold_chunk_ids 由 Codex 据实际 chunk 回填。
- agent_residual 索引开关默认关，绝不进 headline。
