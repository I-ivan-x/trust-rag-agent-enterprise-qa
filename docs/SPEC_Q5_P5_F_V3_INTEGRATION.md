# Batch 5-F Spec: V3 Baseline and Crossed Metrics Integration

版本：v1
日期：2026-07-13
执行窗口：implementation
外部请求：**0**

## 1. 强规则 Headline Baseline

- 将 Batch 5-E fixed-table runtime logic 提升为 V3 `q5_rule_agent` 的正式 policy；
- 必须走同一 tools、validator、completion guard、terminal sink 和 outcome grader；
- `llm_calls=0`、tokens=0；不得读取 Gold/stratum/group/variant tags；
- v1/v2 frozen artifacts 的 rule 语义不变；只影响新 protocol-v3 run；
- strong-rule control 与 headline rule 共享一个纯 runtime 决策核心，防止两份规则漂移。

活动 v3 k=3 上 rule semantic trajectory-qualified success 与 fixed-table solvability 都必须精确为 0.50。

## 2. Crossed Metrics

在 protocol-v3 grader 中从 Gold-only tags 建立六组 within 和六组 cross pairs。每组只有两案均
`trajectory_qualified_success=true` 才记 1：

- `within_policy_adaptation_accuracy`；
- `cross_policy_semantic_sensitivity`。

要求严格检查：每案一组、每组两案、同 family/tool、动作分歧；within 同 variant/不同 state，cross
同 state/不同 variant。缺组、重复、Gold tag 混入 raw/runtime 或不完整 k pairing 均 fail closed。

将 `fixed_table_solvability` 作为独立 control/baseline diagnostic 写入 v3 summary，不得伪装为普通系统
模型指标。更新 report 与 verifier 交叉重算。

## 3. Preflight-v3

- preflight receipt 升级或扩展为明确要求 active dataset provenance v3、protocol-v3 mock anchor；
- 校验本 authoring report 的六个文件哈希；
- 校验 strong-rule 0.50、两轴 group closure、duplicate=0、post-observation terminal=1.00；
- 费用/token 继续 observability-only；本批不得执行 real run。

## 4. Synthetic Matrix

在 implementation commit 上生成完整三个系统、k=3、324-trial protocol-v3 mock，并独立 grade/verify。
预期 fixed-table mock 无法理解交叉政策，因此 G1 可失败；不得为 synthetic G1 修改数据或 prompt。

必须通过：G0/G2/G3/G5、strong-rule=0.50、fixed-table=0.50、duplicate=0、terminal rate=1.00、所有
schema/provenance/safety 门。输出 crossed metrics 的实际值与 per-group 明细。

## 5. 冻结与验收

- 不修改 `data/q5/dev`、Gold、Gate 数值、历史 artifacts 或 q5_test；
- external/LLM requests=0；不添加 case-specific few-shot/答案；
- v1/v2 real runs 与 v2 fixture 继续验签；
- pre-run tamper、metrics tamper、raw Gold leakage、baseline Gold access 均有测试；
- Q5 专项、全量 pytest、Ruff、uv lock、frontend build、release gates 全绿；
- 独立提交并保持 worktree clean，随后交 plan/report 审核，未获批准不得运行 DeepSeek。
