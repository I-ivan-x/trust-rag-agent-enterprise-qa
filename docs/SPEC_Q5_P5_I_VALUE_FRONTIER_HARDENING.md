# Batch 5-I Spec: Cognitive Routing and Value Attribution

版本：v1
日期：2026-07-14
执行窗口：implementation
外部请求：**0**

前置条件：Batch 5-H commit `0792fd37f591f2a60f3f2d13a845fea35a2166e7` 先通过 plan/report 审核。
本批不得与 5-H 审核混为一个提交。

## 1. Cognitive-step Hybrid Routing

将 Hybrid 从 trial-level 固定 policy 改为 step-level policy selection：

- terminal policy block 继续全程 Rule；
- 未完成 required trusted state 时，由 Rule 生成唯一、grounded、read-only observation proposal；
- observation 成功并进入 terminal-only context 后，若 runtime facts 表明需要 policy semantic binding，则
  切换 LLM；
- LLM-only 继续每一步调用 LLM；Rule baseline 继续每一步使用 Rule；
- route decision 只能读取 task/runtime context、conditions、legal actions、completed observations；
- 禁止读取 case id、Gold、stratum、pair/group、expected disposition/action；
- 不增加 step/observation budget、retry、fallback 或 model calls；
- Rule observation proposal 必须经过现有 reauthorization、tool schema validator 与 completion guard；
- terminal disposition 继续经过 v4 compiler、Q4 validator、approval 与 sink。

复用 `policy_events.jsonl.policy_source` 作为 per-step source ledger；不得为旧 artifact 追加字段。必要时新增
独立 sidecar，不破坏 protocol-v4 artifact closure 和 v1-v4 verifier。

## 2. Hash-closed Value Ledger

新增纯离线命令，从一个已通过 `verify_q5_graded_run` 的三系统 run 生成：

```text
value_ledger.jsonl
value_summary.json
value_report.md
value_hashes.json
```

严格要求完整 36 cases x 3 systems x k trial pairing。按 case/run 与 crossed pair/group 输出：

- Rule、LLM-only、Hybrid TQ outcome；
- beneficial/neutral/harmful classification；
- Hybrid observation/terminal policy source；
- oracle outcome 与 Hybrid regret；
- beneficial capture、harmful/neutral exposure；
- calls by cognitive phase；
- incremental successes per 100 LLM calls。

sidecar verifier 必须从 source artifacts 重算并核验 hashes。缺失、重复、额外 trial、改写 source hash、
route event 不完整或系统矩阵不闭合均 fail closed。Oracle/value labels绝不能回流 runtime/router。

## 3. Symbolic Policy Control

在 `q5_semantic_control` 所属边界新增独立 zero-call control：

- 使用通用 clause segmentation；
- 根据 query/observation 中 status、scope 与 policy clause 条件词匹配分支；
- 使用冻结 disposition lexicon 映射到 v4 `Q5PolicyDisposition`；
- 通过相同 read-only tools、compiler、validator 与 outcome grader；
- 不接受 Gold 参数，不访问 case id、stratum、pair/group 或 expected action；
- 输出源码 hash、配置/lexicon、trial rows、semantic/within/cross metrics 与 artifact hashes；
- 对 resource/policy 名改写、case 顺序变化和无关句插入保持行为不依赖 identity；
- 对未知、并列或低置信 clause fail closed 到 human review，不得偷偷调用模型。

新增 source inspection 与 behavioral tests，禁止 `q5-dev-s*`、具体 resource/policy 名或 Gold tag 出现在
control implementation/config。

## 4. 冻结边界

不得修改：

- `data/q5/dev`、archive、Gold、pair、Gate；
- prompt-v4、disposition enum/compiler mapping、tool contracts；
- v1-v4 historical artifacts；
- Rule 与 LLM-only baseline 行为；
- q5_test、confirmatory、freeze/tag。

现有 protocol-v4 mock 必须继续验签。若正式 summary schema 不变，value ledger/control 使用独立 sidecar；
不得为了展示新指标破坏冻结 artifact dispatch。

## 5. Synthetic Acceptance

在 Batch 5-I implementation commit 上运行完整 v4 mock，预期：

- 324/324 trials，三个系统；
- LLM-only calls=132；
- Hybrid observation-planning LLM calls=0；
- Hybrid semantic-binding LLM calls=36；
- Hybrid adversarial LLM calls=6；
- Hybrid total calls=42，call ratio=`0.318182`；
- model-called Hybrid trials=39；
- token ratio `<=0.50`；
- mock task/semantic/pair outcomes不得因路由重构改变；
- observation recall=1.00、duplicate=0、terminal rate=1.00；
- G0/G2/G3/G5 通过；F11/F13/F17、unsafe/schema/transition 全部 0；
- disposition/action consistency=1.00；
- value ledger 与 symbolic control 均可独立验签。

mock 不用于证明 LLM value。Symbolic baseline 是真实 claim feasibility check：若它使新增 claim-readiness
在数学上无足够 headroom，preflight 必须无效并停止，不得运行 DeepSeek。

## 6. Preflight 与机械验收

升级 zero-request preflight，在不改变 provider 配置的前提下额外验证：

- same-commit v4 mock；
- exact per-phase call topology；
- verified value ledger；
- symbolic baseline artifact/source hashes；
- `Q5_VALUE_FRONTIER_STRATEGY.md` 的 claim headroom；
- v1/v2/v3 real 与 v4 mock 历史验签；
- real output directory absent；
- completion/HTTP/model requests 均为 0。

执行 Q5 专项、全量 pytest、Ruff、uv lock、frontend build、6/6 release gates。独立提交、worktree clean，
随后停止并回报；不得执行 DeepSeek/Xiaomi 或自行进入 Batch 5-J。
