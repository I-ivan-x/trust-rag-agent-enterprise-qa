# Agent Reliability Lab：三分钟演示脚本

这是一份可直接照读的 180 秒面试演示稿。公开数字的唯一事实源是
`data/claims/claim_registry.json`；发布与前端验收事实来自
`data/releases/release_manifest_v2.json` 和
`data/releases/clean_clone_receipt_v1.json`。如果本文与 canonical artifact
不一致，以 artifact 为准。

## 面试前 5 分钟 preflight

- 预先启动本地静态页并停在 Hero；90 秒观看预算不包含依赖安装。
- 另开两个只读标签页：`data/claims/claim_registry.json` 与
  `data/releases/release_manifest_v2.json`，便于当场验真。
- 保留 `docs/assets/interview-hero.png` 作为浏览器或本地服务故障时的截图兜底。
- 关闭含 token、`.env`、个人路径或无关客户信息的终端和编辑器面板；演示窗口不展示密钥。
- 确认 `git status --short` 为空、`q5_test` 不存在，并从头试点一次六个页面动作。

## 使用规则

- 全程正好六段，`22 + 23 + 30 + 25 + 50 + 30 = 180` 秒。
- 按时间点切换页面，不临场增加背景故事；按每分钟约 270 个可见字符排练。
- `headline_eligible=true` 只允许在该 Claim 的明确范围内做公开结论，不等于开放世界证明。
- `headline_eligible=false` 的结果只能作为工程信号或解释材料，不能包装成独立 headline。

## 180 秒照读版

### 0:00–0:22｜Hero：先讲问题

**屏幕动作：** 停在 Hero，让面试官看到一句话结论和三个证据数字。

**照读：**

> 多数 Agent 演示只展示成功。我想回答两个更难的问题：模型什么时候有资格执行，团队什么时候有资格公开结论。Agent Reliability Lab 把权限、证据、评测和发布都做成可验证门禁。

**证据边界：** 这是项目定位，不是数值 Claim；`headline eligibility` 不适用。

### 0:22–0:45｜Five Questions：把价值讲成人能理解的问题

**屏幕动作：** 滚动 Five Questions，依次指向 Q1–Q5，不展开卡片细节。

**照读：**

> 页面先给出五个问题：回答能否安全失败，有限恢复是否真有收益，模型能否越权，动作选择是否有用，以及大模型什么时候不可替代。这里正结果、负结果和未评估问题并列；项目不把“做过”写成“证明过”。

**证据边界：** 本段是 14 条 canonical Claim 的问题索引，不把不同 Q1–Q5
范围合并为一个总效果 Claim。

### 0:45–1:15｜Governed Runtime：模型只能提议，主机决定能否执行

**屏幕动作：** 点击“危险路径：尝试绕过审批”，再切回“正确路径：等待审批”；
停在权限检查、拒绝结果、trace ID 和 synthetic provenance。

**照读：**

> 轨迹是合成演示，数字来自冻结评测。模型只提议；主机检查 schema、状态、证据、角色与 capability，审批不足就在副作用前停止。Q4 冻结第二次运行阻断 9/9 未授权动作；没有无证据动作，也没有漏掉未授权升级。这是范围内结果。

**Claim 锚点：**

- `q4.release_reliability`
- 范围：`Q4 frozen ops_test second-run safety floor`
- 数字：`unauthorized_action_blocked=9/9`、
  `F11_action_without_evidence=0/120`、
  `F13_missed_escalation_unauth=0/120`
- Evidence mode：`real`，表示真实 provider/embedding/reranker 执行，不表示生产流量或客户数据
- Headline eligibility：`true`，但只能按上述冻结第二次运行范围表述

### 1:15–1:40｜Reliability Turn：安全成功，不代表选择有用

**屏幕动作：** 切到 Reliability Turn，先指 Q3 的失败，再指 Q4 的冻结复验结果。

**照读：**

> 安全不等于有用。Q3 虽挡住越权，却没过动作选择门。我们不降门槛，只修机制；`ops_test` 首次仍差一例，第二次才过门。两次运行和五条查询修复全部保留，所以这是披露后的机制复验，不是 pristine one-shot holdout。

**Claim 锚点：**

- `q3.action_usefulness`：Q3 real ops development scope，
  `headline_eligible=false`，只用于解释失败转折
- `q4.calibrated_selection`：Q4 frozen `ops_test` second-run scope，
  `precision_authorized=33/51`、`anti_gaming_triad=1/1`、
  `over_escalation_rate=3/60`，`headline_eligible=true`
- Q4 结果真实但样本薄；不得外推为通用 controller 保证

### 1:40–2:30｜Q5 Decision Frontier：知道何时不该调用大模型

**屏幕动作：** 指出 Grammar、Controlled prose、Open semantics、Unsafe 四种路径；
只进入 Controlled prose，依次点 Hypothesis、Real result、Final decision。其余三项不展开。

**照读：**

> Q5 回答何时值得调用大模型：Grammar 走 parser，Unsafe 拒绝，Open semantics 未评估。真实开发运行中，Hybrid 比 LLM-only 少调用，但这不是 held-out 结论；大模型只比强规则多解决 1/12，未过预注册门槛，而版本化 parser 解决受控文本 32/32，剩余 0/32。所以当前范围结论是 scoped negative complete。

**Claim 锚点：**

- `q5.hybrid_efficiency`：protocol-v3 primary real-dev scope，
  calls `78/132`、tokens `66531/103246`，`headline_eligible=false`
- `q5.llm_semantic_uplift`：current real-dev semantic scope，
  uplift `1/12`，低于预注册 `0.10`，`headline_eligible=true`
- `q5.controlled_prose_llm_necessity`：frozen K0U parser-uncovered
  32-case scope，`previously_uncovered_cases_resolved=32/32`、
  `remaining_uncovered_cases=0/32`，`headline_eligible=true`
- `q5.open_world_llm_value`：`not_evaluated`，
  `headline_eligible=false`
- 原 Boundary F 的 `30/32` 保持为历史层；addendum 是后续独立证据，不覆盖原结果

### 2:30–3:00｜Evidence Ledger：让结论也通过发布门

**屏幕动作：** 打开任意 Claim，依次指出 artifact、SHA-256、run ID、commit、
evidence mode、scope 和 headline eligibility。

**照读：**

> 最后看 Evidence Ledger。每个公开结论都绑定 claim ID、artifact hash、run、commit、scope 和 headline eligibility，生成器与 CI 拒绝漂移。价值不只是模型不越权，也包括发布不失真，以及团队知道何时停止。

**证据边界：** Claim registry 当前含 14 条 Claim、11 个唯一 tracked source
artifact。Detached no-hardlinks clean clone 的发布验收是独立工程事实，不应冒充模型能力 Claim。

## 演示结束后的唯一补充句

如果面试官追问“所以大模型没有价值吗”，只回答：

> 不是。被否定的是冻结受控范围内的必要性和当前 real-dev 范围内的预注册 uplift；open-world LLM value 没有评估，因此我明确不做那个外推。
