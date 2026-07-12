# TrustRAG 工程纪律与高效执行记录

盘点日期：2026-07-12
证据范围：`2026-06-10` 至 `2026-07-12` 的 Git 历史、项目文档、评测代码、测试与发布标签
用途：说明项目如何被组织、推进、验证和收口，以及这种执行方式体现的工程素养

> 本文不是工作量陈列，也不以“写了很多代码”证明能力。它只记录能从仓库复核的执行行为，
> 并明确区分已经落地的纪律、仅写入原则但尚未完全兑现的制度，以及当前仍需修复的秩序缺口。

------

## 1. 结论

TrustRAG 的项目秩序不是传统的“先列功能，再逐项打勾”，而是围绕一个可守住的工程论断组织：

> 在明确条件下，证明 Agent 的回答和动作比 naive 实现更可信；在证据不足时拒绝超卖，
> 在结果失败时保留失败、定位机制并重新验证。

从 Git 历史可以观察到稳定重复的交付闭环：

```text
原则 / 目标
  -> 设计冻结
  -> 实现规格
  -> 小步代码提交
  -> 零 token 诊断或测试预检
  -> 真实 run
  -> 失败归因与报告
  -> 文档收口
  -> release tag
```

这套方法体现的核心不是单纯开发速度，而是四种能力同时存在：方向判断、实验纪律、范围控制和
可复现交付。AI 被用于提高实现与分析吞吐量，但结果门槛、范围取舍和正负结论没有外包给 AI。

------

## 2. 可核验的项目规模

以下数字来自当前分支在盘点日的机械统计；阶段名 Q1-Q4 是项目工程阶段，不代表四个自然季度。

| 证据 | 数量 / 时间 | 它说明什么 |
| --- | ---: | --- |
| Git commits | **107** | 交付被拆成可审查的小步，而非一次性大提交 |
| 有记录的开发跨度 | **2026-06-10 至 2026-07-12** | 33 个自然日内完成系统、评测、治理、可靠性、展示与 Q5 Agent Infra 迭代 |
| 正式阶段标签 | **4** | `v0.3-q1-hard-demo`、`v1.0-q2-agentic-eval`、`v2.0-q3-action-governance`、`v3.0-q4-reliability` |
| 阶段性标签 | **6** | ingestion、retrieval、generation、trust gates、eval 分阶段冻结 |
| `docs/*.md` | **70（含本文及 Q5 文档）** | 设计、协议、规格、报告、失败分析和交接材料分层保存 |
| 实现规格文档 | **21** | 高风险功能通常先写契约，再进入代码 |
| 可执行脚本 | **28** | ingest、index、eval、leakage、ablation、diagnostic、release gate 均可命令化 |
| Python app 代码 | **20,605 行** | 覆盖完整 RAG、Agent、治理、评测与可观测模块 |
| Python test 代码 | **13,081 行** | 测试代码约为 app 代码的 63%，质量投入不是尾部补丁 |
| 全量回归 | **517 passed, 1 skipped** | 2026-07-12 独立实跑；另有 23 条 warning |

这些数字只证明项目具有持续投入和结构化产物，不单独证明质量。质量结论仍以真实 run、评测边界、
失败分析和可复现命令为准。

------

## 3. 纪律一：先定义可守住的论断，再决定做什么

[`PRINCIPLES.md`](PRINCIPLES.md) 把项目交付物定义为“一个站得住的论断”，而不是功能数量。
这个原则在后续执行中出现了可验证的对应行为：

- README 同时列出正结果和负结果，没有只展示最好看的指标。
- `grounded_correctness` 被设为承重指标，raw correctness 只用于污染分析。
- `citation_valid=1.00` 被限定为结构有效性，没有包装成人工语义准确率。
- Q2 检索恢复 Agent 没有证明增益，结论被明确写成“增益证伪”。
- Q3 动作安全达到目标但选择质量不足，anti-gaming triad 保持 False，没有抢先宣布成功。

这说明项目的优先级由“什么结论可以被证据支撑”决定，而不是由“什么功能更像热门 Agent”决定。

------

## 4. 纪律二：高成本决策先冻结，低成本实现快速迭代

项目对不可逆决策和可逆实现使用不同节奏：

- schema、eval protocol、gold、成功阈值、数据切分先写设计或预注册，再进入实现。
- 模块内部实现、prompt 和局部路由允许快速修改，但修改必须重新过测试和评测。
- Q2、Q3、Q4 都有独立 design/spec 文档；Q4 在逻辑修改前提交成功标准和 held-out 列表。
- [`Q4_P4_FREEZE.md`](Q4_P4_FREEZE.md) 保存冻结 commit、配置、阈值、模型、索引和 dev 读数。
- [`run_manifest.py`](../app/eval/run_manifest.py) 将 commit SHA、模型、index fingerprint、seed、k、
  cost、latency 和阈值快照写入 run provenance。

典型例子是 Q4：先做零 token 根因诊断，再扩评测集和预注册，只在 dev 上校准，随后冻结配置并跑
held-out；即使 test 第一次未过，第二次机制修正和两次结果也都被保留披露，而不是覆盖历史。

------

## 5. 纪律三：主动砍掉没有证据价值的工作

高效性最清楚的证据不是“做得快”，而是多次停止了看似高级但证据不足的方向：

| 决策 | 触发证据 | 处理 |
| --- | --- | --- |
| 不部署 LLM judge | 三候选均未过判别力门，wrong-side probe 0/2 | judge-dependent metric 和 runtime verifier 一并 descoped |
| 砍 version-scoped retrieval 动作 | hard-negative 重写后未证明版本型 top-5 崩塌 | 从 Q2 动作空间删除，不为“Agent 感”保留 |
| 不宣称 Agent 增益 | gated 0.2273 vs agentic 0.2727，仅一例差距且 rule=LLM | 作为负结果进入报告和 ADR |
| 不做多 Agent | 无证据表明它解决当前瓶颈 | 保持单 Agent 和有限动作预算 |
| 不做统一 eval harness 大重构 | Q4 的承重目标是选择校准 | 明确列入非目标，避免基础设施稀释实验主线 |
| 不把 mock 当正式结果 | mock 只服务测试、smoke 和本地 demo | `mock_used` 与 `headline_eligible` 由代码联动 |

[`ROADMAP.md`](ROADMAP.md) 不只记录“做什么”，还记录砍序、不可砍底线和落后时的降级路径。
这体现的是资源配置能力：完整证据链优先于功能覆盖率，承重实验优先于展示层和框架重构。

------

## 6. 纪律四：先用低成本诊断缩小问题，再花真实模型预算

项目持续使用“由便宜到昂贵”的执行顺序：

- retrieval-only ablation 用于回答检索问题，不为不需要生成的问题支付 LLM 成本。
- Q4-P1 先跑零 token 条件检测，确认 `flag_stale` 是检测死路而不是 LLM 选择失败。
- Agent ablation 前先跑 diagnostic precheck，确认动作触发面和可恢复案例数量。
- mock provider 用于单测和 Docker smoke，但通过代码禁止进入 headline。
- 无法部署的 judge 在小规模锚点和 probe 阶段就被停止，没有继续全量回填。
- 每类真实 run 记录调用数、token、run_id 和 eligibility，便于复查成本与结论边界。

这不是简单的“省 token”，而是先验证实验是否能回答问题，再支付昂贵执行成本。

------

## 7. 纪律五：把评测本身当成会失败的系统

项目没有假设 eval 天然可信，而是为评测建立了自己的治理层：

- corpus author / eval author 过程隔离。
- leakage checker 同时检查“泄漏过多”和“问题没有可检索信息”。
- real、mock、fixture、external、hard-negative、red-team 按用途隔离，禁止跨边界解释。
- summary 写入 `headline_eligible`、`mock_used`、`vector_unavailable`、`expected_rewrite_used`。
- [`check_release_gates.py`](../scripts/check_release_gates.py) 对 F11、F13、triad、mock、vector fallback
  和 leakage 执行机器判定。
- pass^k、trajectory attribution、F1-F13 taxonomy 将不稳定性和动作失败拆到可定位层级。

最能说明纪律性的事件是原 hard-negative split 自身设计失败：项目没有把错误数据解释为系统鲁棒性差，
而是裁定 F8 eval mismatch、重写 query、执行双向 leakage 检查并重新测量。这说明“审计自己”不是口号。

------

## 8. 纪律六：提交历史保持因果链，而不是只保留最终答案

Git 历史中的多条链路都保持了相似结构：

| 日期 | 代表性闭环 |
| --- | --- |
| 2026-06-10 至 2026-06-14 | foundation -> ingestion -> retrieval -> generation -> trust gates -> real eval -> Q1 release |
| 2026-06-15 至 2026-06-24 | judge gate failure -> descoped；hard-negative 重写；typed-action Agent -> ablation -> Q2 tag |
| 2026-06-24 至 2026-06-25 | Q3 design/spec -> condition/sink/validator/controller -> real governance run -> Web console -> Q3 tag |
| 2026-06-25 至 2026-06-26 | Q4 diagnosis -> preregistration -> dev calibration -> freeze -> held-out -> OTel/manifest/gates -> Q4 tag |
| 2026-06-29 | showcase plan -> snapshot data -> staged frontend implementation -> v2 focus redesign |
| 2026-07-10 至 2026-07-12 | Q5 design freeze -> Batch 0-4 -> real-dev 负诊断 -> protocol v2 -> v1 archive -> counterfactual dev v2 |

提交信息通常能直接回答“这是设计、实现、评测还是报告”，并保留关键负结果，例如
`no judge deployed`、`agent gain falsified`、`negative->positive`。这使 Git 本身成为决策审计记录的一部分。

------

## 9. AI 协作方式体现的效率与所有权

项目明确采用 AI 协作，但没有把“AI 生成速度”冒充个人工程能力。仓库所体现的有效协作模式是：

- Codex 负责主要代码执行，Claude 参与设计/文档，Owner 负责取舍、标注、冻结和验收。
- AI 产出的 eval case、gold 和高成本协议被视为高风险内容，需要独立检查或 Owner 签字。
- 代码正确性由测试兜底，结论正确性由真实 run、人工审计和报告边界兜底。
- 当 AI 建议与实测结果冲突时，以 run 证据为准，例如不部署 judge、不保留无依据动作。

因此，这个项目可用于说明一种更准确的能力：**能把 AI 作为高吞吐执行工具，同时通过契约、评测和
冻结机制保留人类对方向与结论的所有权。**

------

## 10. 这套秩序体现的职业能力

| 能力 | 仓库证据 |
| --- | --- |
| 技术判断 | 能区分检索、生成、策略、评测和运行时问题，不用 prompt tuning 解释所有失败 |
| 实验素养 | baseline、消融、预注册、held-out、pass^k、人工锚点、负结果披露 |
| 项目管理 | 分阶段目标、依赖链、Owner、验收标准、scope review、砍序、release tag |
| 风险意识 | ACL/state/evidence gate、validator、HITL、red-team、mock/headline 隔离 |
| 成本意识 | zero-token precheck、retrieval-only run、小样本 judge gate、调用量预算 |
| 工程质量 | 517 passed / 1 skipped、Ruff 全绿、Docker smoke、run manifest、trace、失败分类与回归检查脚本 |
| 沟通能力 | README、技术 ADR、评测报告、失败报告、Interview QA、Web showcase 分别服务不同读者 |
| 迭代能力 | Q2 证伪 Agent 增益，Q3 找到新价值面，Q4 把明确负结果修成受约束正结果 |

------

## 11. 当前尚未完全兑现的秩序

为了让本文在面试中可守住，以下缺口不能省略。截至 2026-07-12：

- `PRINCIPLES.md` 要求维护 `DECISIONS.md` 和 `FAILURE_JOURNAL.md`，但仓库中没有这两个文件；
  决策实际散落在 ROADMAP、ADR、freeze 和 report 中，内容存在，但索引形式没有兑现。
- `.github/workflows/ci.yml` 已接入 locked dependency install、Ruff、全量 pytest、synthetic release
  gates 与 frontend build；但真实模型评测仍是受控人工运行，不能把普通 CI 绿灯等同于 real-run 结论。
- 全量测试为 517 passed / 1 skipped，但仍有 23 条 warning，需要继续清理依赖弃用、mock 提示和缓存权限问题。
- 当前工作位于 `codex/q5-adaptive-agent`，Q5 晚于 `v3.0-q4-reliability`，但尚未通过 real-dev freeze，
  因而不能创建新 release tag。
- Q5 v2 synthetic k=3 首次因 G3 token ratio `0.65233` 被锁；C3 在不改数据、Gold、Gate、路由或
  baseline 的条件下压缩 schema annotation metadata，复验降至 `0.646985` 后才解锁 DeepSeek real-dev。
  唯一 real-dev 随后仍因 G1/G3 失败被裁定 NOT FREEZE READY；项目停止追加 real run，并继续锁定
  q5_test、confirmatory 与 headline。这避免了用 synthetic 成功替代真实模型证据。
- Q4 held-out 结果真实但样本薄、同语料表面且运行过两次；它展示纪律，但不能替代下一轮独立外部评测。

这些缺口不推翻前面的执行证据，但它们构成下一阶段启动前的 P0：先让仓库当前状态重新符合项目自己
定义的标准，再扩展新能力。

------

## 12. 简历与面试表达

简历中的短句可以写为：

> 建立 evidence-driven 的 Agent 研发流程，以设计冻结、预注册评测、零 token 诊断、消融实验、
> run manifest 和机器化发布门管理 AI 协作开发；33 天形成 107 次可审查提交、4 个阶段 release，
> 完整测试 517 passed，并将未达门槛的 judge/Agent 能力主动证伪、降级或锁定。

面试中的一分钟表达：

> 我在这个项目里刻意把“开发速度”和“结论可信度”分开管理。可逆的实现快速迭代，不可逆的 schema、
> gold、评测阈值先冻结；真实 LLM run 前先用 retrieval-only 或 zero-token precheck 缩小问题；没有过
> 判别门的 judge 就不上线，没有测出增益的 Agent 就写成负结果。AI 提高了执行速度，但功能是否保留、
> 什么数字能写进简历，最终由预注册门槛、真实 run 和 Owner 验收决定。

最适合用本文证明的不是“我很勤奋”，而是：**我能把一个快速变化、强依赖 AI 协作的项目组织成
有边界、有证据、有取舍、能复盘的工程过程。**
