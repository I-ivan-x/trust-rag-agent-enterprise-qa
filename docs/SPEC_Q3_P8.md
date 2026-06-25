# SPEC Q3-P8：Web 动作控制台

版本：v1-q3-p8-impl
状态：实现规格（freeze-ready）。依赖 P1–P4（govern/detect/approvals/sinks）+ P7（govern_runner）。
对应：`Q3_ACTION_GOVERNANCE_DESIGN.md` §9。
分工：**Codex** 做 FastAPI 后端（§1）+ 后端测试（§4，纯 Python，无前端工具依赖）；
**Claude 会话** 做前端 4 视图（§2）。前端实现工具不在本设计文档约束范围内（保持工具无关；
具体执行工具由执行指引另行约定，不写入本设计正文）。

------

## 0. 定位与目标

```text
P8 = 把"读→判→动→治"做成可演示的 Web 控制台，直接解决"demo 体现不出 agent"。
后端：复用 detect_conditions / govern / approvals / sinks，零新业务逻辑——只加 HTTP 层。
前端：消费后端 API，呈现 4 个视图。可演示交付物，非 eval 支撑核心（与指标层解耦）。
演示主线（与 P7 诚实框架一致）：把"安全性"演活——越权被拦、无证据不动、每动作可审计，
  比"动作选得多准"更是看点。
```

------

## 1. 后端 API（`app/api/govern_routes.py`，挂进 `create_app()`）

镜像 `app/api/chat_routes.py` 的 `APIRouter` 体例；sink 指向受控 action_store（演示目录，
可经 deps 注入隔离路径）。所有端点纯读/纯写本地 sink，无外部系统。

| 方法 路径 | 作用 | 复用 |
| --- | --- | --- |
| `POST /govern/run` | 单 query 跑 读→判→动→治，返回 GovernanceOutcome（含 trace + 拟议动作 + 路由结果） | `run_governance_case` 的在线变体（默认 rule 控制器，确定性；`?controller=llm` 可选） |
| `GET /govern/pending` | 列待审批（pending_approval）项 | `approvals.list_pending` |
| `POST /govern/pending/{record_id}/approve` | 批准 → committed | `approvals.approve_pending` |
| `POST /govern/pending/{record_id}/reject` | 拒绝 → dropped | `approvals.reject_pending` |
| `GET /govern/audit` | 全审计链（tickets/alerts/annotations/escalations 合并按时间） | 读 action_store |
| `GET /govern/audit/blocked` | 越权/无证据拦截日志（authorized=False 或 validator forced 的 escalation） | 读 escalations sink + 过滤 |

响应模型用 pydantic（沿用项目 schemas 风格）；`/govern/run` 请求体 = `{query, user_role, controller?}`。

### 1.1 后端不变式（务必）

```text
- 不新增治理逻辑：动作合法性/风险/越权一律走 P3 validator + govern()，HTTP 层不得旁路。
- approve 仅作用于 pending_approval 记录；对 committed/escalated/dropped 调用 → 4xx，不静默改。
- 演示 sink 与 P7 run 的 sink 目录隔离，避免互相污染。
- 不引入鉴权系统：user_role 由请求显式带（演示用），不是真实身份认证。
```

------

## 2. 前端控制台（4 视图，工具无关）

```text
1. 读→判→动→治 时间线（单 case trajectory）
   输入一个 query + user_role → 调 /govern/run → 四阶段时间线：
   Read(检索命中) → Detect(conditions + authorized?) → Act(proposed_action + controller_source)
   → Govern(validator_verdict + risk_tier + approval_state + forced?)。
   每步显示证据 citation（context-only）与 gate 决策。

2. 待审批队列
   /govern/pending 列表；每项"批准/拒绝"按钮 → approve/reject 端点 → 刷新。
   体现"高风险动作（ticket/alert）人审 commit 后才生效"。

3. 审计链
   /govern/audit 时间线：每动作 proposed→validated→tier→executed|blocked→sink_record_id。
   append-only、可追溯。

4. 越权拦截日志
   /govern/audit/blocked：被前置门挡下的越权/无证据动作。
   这是 fail-closed 的可视证据，演示主打这一屏。
```

### 2.1 内置演示脚本（确定性、讲完整故事）

预置 ~5 个 canned query（取自 `ops_runbook_action_v1` gold），一键依次跑出五种结局：

```text
flag_stale（auto 自动提交）          ← ora-001 类（admin 问废弃流程）
open_remediation_ticket（→pending）  ← ora-004 类（admin 报配置违规）→ 演示人审批准
send_alert（→pending）               ← ora-007 类（admin 报 active-active 冲突）
escalate（越权被拦）                  ← ora-009 类（viewer 请求开工单）→ 越权拦截屏高亮
no_op（系统正常不乱动）              ← ora-013 类（admin 问标准滚动更新）
```

------

## 3. 范围、砍序、非目标

```text
期中 scope review 砍序（设计 §12）：
  落后 ≤1 周：前端降级为"仅视图 1 时间线 + 视图 4 拦截日志"，待审队列交互砍（approve 走 API/curl）。
  落后 >1 周：砍前端，仅保留 §1 后端 API + Swagger 演示（视图能力由 API 自描述承载）。
不可砍底线：/govern/run + /govern/audit/blocked 存在（安全性可演示）；后端不旁路 validator。
非目标：鉴权/多用户、真实外部 sink、移动端、前端单测覆盖率指标、SSR/SEO。
```

------

## 4. 测试（Codex）

```text
后端（FastAPI TestClient，沿用现有 api 测试套路）：
  test_govern_run_returns_outcome        rule 控制器跑通，返回四阶段字段
  test_govern_run_unauthorized_blocked   viewer 请求高风险动作 → escalated，未落副作用 sink
  test_pending_list_then_approve         ticket → pending → approve → committed
  test_pending_reject_drops              pending → reject → dropped
  test_approve_on_committed_4xx          对非 pending 记录 approve → 4xx
  test_audit_blocked_filter              越权记录出现在 /govern/audit/blocked
前端：演示交付物，不要求单测覆盖率；保证 4 视图可手动走通 canned 脚本即可。
```

------

## 5. 验收

```text
[ ] app/api/govern_routes.py 挂进 create_app()；§1 六端点 + §1.1 不变式
[ ] 前端 4 视图消费 API；§2.1 canned 演示脚本一键可跑
[ ] §4 后端测试全过；ruff 干净；pytest 全绿；Q2 + P1–P7 回归不变
[ ] 演示可呈现：越权被拦 + 无证据不动 + 高风险人审 + 审计链可追溯
对齐 Q3 Gate ⑥：Web 控制台可演示 读→判→动→治 + 待审 + 审计链。
```

非目标（最后一程）：README / EVALUATION_REPORT / TECHNICAL_DESIGN（ADR-012~014）+ tag
`v2.0-q3-action-governance`（P9）。
