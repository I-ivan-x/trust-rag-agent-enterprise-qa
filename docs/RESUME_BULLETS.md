# Agent Reliability Lab：岗位化简历 Bullet

以下三条分别面向后端、AI Infra 和平台可靠性岗位。它们不是新的事实源：
Claim 数字以 `data/claims/claim_registry.json` 为准，发布验收数字以
`data/releases/release_manifest_v2.json` 和
`data/releases/clean_clone_receipt_v1.json` 为准。

## 后端 / Agent Platform

**简历短版：**

> 构建受治理 Tool-using Agent 运行时，以 typed schema、权限再授权与人工审批在已披露的冻结评测第二次运行中阻断 9/9 未授权动作。

**面试展开版：**

> 设计并实现 host-enforced 的 tool-using Agent 运行时，将 typed schema、状态机、证据与 ACL/capability 再授权、人工审批和 side-effect guard 串成 fail-closed 执行链；在已披露的 Q4 冻结 `ops_test` 第二次运行中阻断 9/9 未授权动作，并将无证据动作与未授权漏升级分别保持为 0/120。

**证据合同：**

- Claim：`q4.release_reliability`
- Scope：`Q4 frozen ops_test second-run safety floor`
- Evidence mode：`real`（真实 provider/embedding/reranker 执行；不是生产流量或客户数据）
- Headline eligibility：`true`
- 限定：首次失败、机制修正与查询修复均已披露；这不是 pristine one-shot holdout 或开放世界安全保证
- Source：`data/claims/source/q4-p5-selection-calibrated/summary.json`

## AI Infra / Evaluation

**简历短版：**

> 在受控文本范围用版本化 parser 解掉 32/32，并因 LLM 语义增益仅 1/12、未过预注册门槛而停止扩大无证据支持的模型路径。

**面试展开版：**

> 建立预注册、成对对照和 Decision Frontier 评测，在当前 real-dev 语义分层中记录 LLM uplift 仅 1/12、低于冻结的 0.10 门槛；随后以版本化 deterministic parser 在 frozen controlled-prose 范围解决 32/32 案例、剩余 0/32，据此关闭该受控文本轨并保持 K1=false，而不是扩写证据不支持的价值 Claim。

**证据合同：**

- Claim：`q5.llm_semantic_uplift`
  - Scope：protocol-v3 primary real-dev run 的 semantic stratum
  - Result：`1/12`，低于 preregistered `0.10`
  - Headline eligibility：`true`，只允许作为 current-scope 负结果
- Claim：`q5.controlled_prose_llm_necessity`
  - Scope：frozen K0U parser-uncovered 32-case controlled-prose scope
  - Result：`previously_uncovered_cases_resolved=32/32`、
    `remaining_uncovered_cases=0/32`
  - Headline eligibility：`true`，只允许作为 frozen-scope 负结果
- Source：
  - `data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/summary.json`
  - `data/claims/source/q5-dev-v3-real-deepseek-v4-flash-e54c42e-primary-k3/gates.json`
  - `data/eval_runs/q5-boundary-f-addendum-z-a/addendum_metrics.json`
- 限定：`q5.open_world_llm_value=not_evaluated`；不得写成“大模型没有价值”

## 平台可靠性 / Release Engineering

**简历短版：**

> 建立哈希证据、CI drift gate 与 clean-clone manifest，使 14 条公开结论可追溯，并在 detached 本地 clean clone 中连续三次通过 Lighthouse ≥90。

**面试展开版：**

> 构建 schema 驱动的 Claim registry、SHA-256 evidence receipts、生成器/CI drift gate 与 detached clean-clone release manifest；将 14 条公开 Claim 绑定到 11 个 tracked source artifacts，并在 0 次模型及评测外部请求下通过 6/6 release gates、Playwright 55 passed/14 conditionally skipped 和连续三次 Lighthouse performance ≥90。

**证据合同：**

- Evidence：
  - `data/claims/claim_registry.json`
  - `data/releases/release_manifest_v2.json`
  - `data/releases/clean_clone_receipt_v1.json`
- Scope：detached `git clone --no-hardlinks` 对 manifest tested commit 的可复现验收
- Evidence mode：release/operational verification
- Headline eligibility：`N/A`；这是工程交付事实，不是模型能力 headline
- 同批 acceptance：Accessibility `100/100/100`、release gates `6/6`、
  model requests `0`、evaluation-external requests `0`

## 可在面试中展开、但不要塞进简历主句的结果

| 结果 | 为什么不能升级为独立简历 headline |
| --- | --- |
| Q5 Hybrid calls `78/132`、tokens `66531/103246` | `q5.hybrid_efficiency` 只在 protocol-v3 primary real-dev scope 得到展示，`headline_eligible=false` |
| Q5 schema/transition safety 在 108 次 real-dev trials 中观察到零项对应失败 | `q5.schema_transition_safety` 是开发范围工程信号，`headline_eligible=false`，零观察失败不是开放世界保证 |
| Q5 selective runtime 与 observation adaptation | 两项均为 named real-dev scope 内的 demonstrated result，`headline_eligible=false` |
| Open-world LLM value | `not_evaluated`，不得从 controlled-prose 结果外推 |

## 禁止使用的夸大写法

- 不写“证明 Agent 永远不会越权”；应写“在已披露的冻结 Q4 `ops_test` 第二次运行中阻断 9/9”。
- 不写“证明大模型无用”；应写“当前 real-dev uplift 未过门槛，controlled-prose
  necessity 在冻结范围被否定，open-world 未评估”。
- 不把 real-dev efficiency 写成 held-out product headline。
- 不把原 Boundary F `30/32` 改写掉；addendum `32/32` 是后续独立证据层。
- 不创建或暗示 `v4.0`；最新稳定产品 release 仍为
  `v3.0-q4-reliability`。
