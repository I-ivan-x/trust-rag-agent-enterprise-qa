# Q5 Value Frontier Strategy

版本：v1
日期：2026-07-14
状态：**FROZEN BEFORE FIRST V4 REAL RUN**

## 1. 核心判断

Q5 的最终命题不应写成“有限测试集在数学上只有 LLM 能解决”。任何有限数据都可以被 case table
硬编码。可辩护的工程命题是：

> 在冻结的、无 Gold 的通用非 LLM baseline 下，LLM 对未结构化 policy 与动态 observation 的组合
> 解释产生可复现增量；Hybrid 只在该认知阶段调用 LLM，并以更少调用接近逐案 oracle 的效果。

当前系统已经证明安全、工具闭环、协议可验签和 task-level call avoidance，但还缺少两份直接证据：

1. LLM 调用是否落在实际产生正增量的任务边界，而不只是 `semantic` 标签；
2. 一个读取 policy 文本的通用 symbolic baseline 是否也能解决 crossed semantics。

## 2. 实际资产盘点

| 现有资产 | 已具备能力 | 尚未转化的价值 |
| --- | --- | --- |
| Rule/LLM-only/Hybrid 完整同案矩阵 | 每个 case/run 都能做 outcome counterfactual | 尚未生成 beneficial/neutral/harmful value ledger |
| `policy_events.jsonl` | 每一步已有 `policy_source`、proposal 与 context version | Hybrid 当前只记录整条 route，未展示 step-level cognitive routing |
| Rule observation recall=1.00 | 工具选择、参数 grounding 与 completion guard 已可靠 | 仍让 LLM 为 semantic case 支付一次可由规则完成的 observation-planning call |
| crossed pair tags/metrics | 能分别控制 policy 与 observation | 尚未把 pair-level LLM value 与 router capture 关联 |
| fixed-table、escalate-all、always-human controls | 已攻击状态表与安全投机 | 尚缺读取自然语言 policy 的强非 LLM baseline |
| v1-v4 verifier 与 replay | 历史 artifact 可在新诊断下重算且不篡改 | 尚未包装为“evaluation migration / forensic replay”亮点 |
| Q5 tool OTel + trajectory/policy events | 运行事实完整 | Q5 还没有 route -> observe -> bind -> compile -> validate 的统一 trace/demo |
| Q4 Astro trajectory player | 已有成熟招聘展示组件 | 仍展示 Q4 rule 治理，没有呈现 Q5 的 LLM value frontier |

## 3. 候选亮点取舍

| 候选 | 招聘/证明价值 | 工程量 | 风险 | 决策 |
| --- | --- | --- | --- | --- |
| Cognitive-step routing | 极高：直接回答 LLM 在哪一步有用 | 中 | 路由状态机回归 | **下一批实施** |
| Counterfactual value ledger | 极高：从标签路由升级为实际 outcome attribution | 中低 | 指标被误作在线 oracle | **下一批实施** |
| Symbolic policy baseline | 极高：主动抵御“正则也能做”攻击 | 中 | baseline 可能击败 LLM | **下一批实施** |
| Q5 unified trace graph | 高：Agent Infra 可观测性 | 中 | 干扰 real-dev critical path | freeze 后实施 |
| Q5 interactive value demo | 极高：面试可见性 | 中 | 数据在 freeze 前反复变化 | test 结果后实施 |
| Replay/migration case study | 高：评测基础设施辨识度 | 低 | 主要是包装而非新能力 | final report/demo 实施 |
| Policy-only/model context ablation | 中高：补充因果证据 | 高 | 扩大模型 runs 与 protocol | 仅在主结果仍有歧义时启用 |
| Confidence calibration/learned router | 中 | 高 | 小数据下伪校准 | 不进入 Q5 主线 |
| Memory、多工具规划、分布式 runtime | 低于当前命题 | 极高 | 稀释项目主线 | 不做 |

## 4. 最关键的架构升级

当前 Hybrid 在 trial 开始时一次性选择 policy：semantic case 由 LLM 同时选择 observation tool 与 terminal
action。v4 mock 中 Hybrid 的 78 calls 可分为：semantic 72、adversarial 6；semantic 的 72 calls 中一半
用于 observation planning，而 Rule 已经在相同工具合同上达到 observation recall=1.00。

目标架构：

```text
Step 1 unresolved state
  deterministic router -> Rule observation planner -> typed read-only tool

Step 2 trusted state complete
  runtime-only semantic-binding fact -> LLM policy disposition
  -> deterministic action compiler -> validator -> approval/sink
```

LLM-only 保持两步都调用模型，作为 control；Rule 保持全规则 baseline；Hybrid 在 semantic trials 只保留
一次 terminal semantic-binding call。按当前 36x3 topology，预期 Hybrid calls 从 78 降至 42，call ratio
从 `0.590909` 降至 `0.318182`，同时不改变 observation、Gold、prompt-v4、工具或 Gate。

这比 task-level router 更能体现 Agent：同一 trajectory 会随着 trusted state 的获得切换认知执行器。

## 5. Counterfactual Value Ledger

Value ledger 只能作为离线、verified-run diagnostic，禁止在线读取：

- `beneficial`：LLM-only TQ > Rule TQ；
- `neutral`：两者相同；
- `harmful`：LLM-only TQ < Rule TQ；
- `oracle`：逐 case/run 选择 Rule 与 LLM-only 中更好的 outcome，仅作不可部署上界；
- `hybrid_oracle_regret`：oracle success - Hybrid success；
- `beneficial_value_capture`：Hybrid terminal LLM route 捕获的 beneficial cases；
- `harmful_llm_exposure`：Hybrid terminal LLM route 落在 harmful cases；
- `neutral_llm_exposure`：如实报告，但不机械视为错误，因为 ex ante policy family 可能仍需解释；
- `incremental_success_per_100_calls`：相对 Rule 的成功增量 / LLM calls。

同时按 crossed pair/group 计算 frontier value。单 case 上 Rule 偶然命中不代表该 policy family 可由状态表
解决；只有完整 pair success 才能判断 policy/state interaction。

## 6. Strong Symbolic Baseline

新增通用、透明、零模型调用的 policy parser control：

- 输入只能是 query、authorized evidence、trusted observation 与通用 action ontology；
- 以通用 clause segmentation、状态/scope overlap 和 disposition lexicon 选择 policy branch；
- 禁止 case id、resource-specific map、Gold、stratum、pair/group tag 与 expected action；
- 与 Rule 一样走 tools、compiler、validator 和 outcome grader；
- 算法与 lexicon 在下一次 real-dev 前冻结并完整输出源码/provenance。

它不是为了故意做弱。如果它解决 dev-v4，则当前任务不支持“LLM 必要”主张，应在发送新的真实请求前
停止。这一失败仍是高价值结论。

## 7. 新增 Claim-readiness

不修改既有 G0-G5。除原 v4 readiness 外，LLM-value headline 还必须满足：

```text
hybrid_semantic_TQ >= symbolic_semantic_TQ + 0.10
hybrid_within_pair_success >= symbolic_within_pair_success + 0.166667
hybrid_cross_pair_success >= symbolic_cross_pair_success + 0.166667
beneficial_value_capture = 1.00
harmful_terminal_llm_exposure = 0
hybrid_oracle_regret <= 0.027778   # 最多 1/36 case
hybrid_observation_planning_llm_calls = 0
hybrid_semantic_binding_llm_calls = 36  # dev k=3
```

若 symbolic baseline 没有足够 headroom 使上述门槛可达，preflight 必须 fail closed。dev bootstrap CI
仍允许跨 0；正式 test headline 继续受原 G0-G5、run discipline 与 cross-family confirmation 约束。

## 8. 后续顺序

1. 审核已实现但尚未在本窗口裁决的 Batch 5-H commit `0792fd3`；
2. Batch 5-I：cognitive-step routing、value ledger、symbolic baseline，external requests=0；
3. 通过后才批准 Batch 5-J：唯一一次 v4 primary real-dev；
4. 若 real-dev 与 strong baseline readiness 均过，freeze implementation/prompt/baselines；
5. plan/report 独立 author sealed q5_test，再执行 one-shot primary + Xiaomi confirmatory；
6. 结果冻结后补 Q5 unified trace、interactive value demo、简历与 tag。
