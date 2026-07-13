# TrustRAG 最新成果与网页端 Demo 整理

整理日期：2026-07-13
最新稳定标签：`v3.0-q4-reliability`；活动研发阶段：Q5 Agent Infra（未冻结）

本文是项目最新展示入口：面向招聘展示、项目复盘、下一位协作者快速接手。完整实验细节仍以
`EVALUATION_REPORT.md`、`FAILURE_ANALYSIS.md`、`TECHNICAL_DESIGN.md` 为准。

------

## 1. 项目一句话

TrustRAG 是一个 reliability-first 的企业文档 RAG-Agent：它不只回答问题，还用 fail-closed
信任门、动作治理、真实 run 评测、可观测 trace 和 CI 硬门来证明自己什么时候该答、什么时候该拒、
什么时候该把动作交给人。

最重要的差异化不是“做了 RAG”，而是：

- 正结果有真实 run 和 run_id 支撑。
- 负结果不隐藏，进入 F1-F13 failure taxonomy。
- 一个 Q3 负结果在 Q4 被真实机制修复翻正，且在留出 test 集验证。
- 网页端 demo 已经把这条 Q1-Q4 叙事做成可展示的作品站。

------

## 2. 最新可引用结果

| 阶段 | 结论 | 可引用数字 | 证据入口 |
| --- | --- | --- | --- |
| Q1 `v0.3-q1-hard-demo` | 可信 RAG + 反自欺评测闭环跑通 | false-answer rate **0.00**；citation structural validity **1.00**；grounded correctness **0.24** 与 false-refusal **0.46** 成对引用 | `README.md`、`EVALUATION_REPORT.md`、`FAILURE_ANALYSIS.md` |
| Q2 `v1.0-q2-agentic-eval` | 类型化 agent 做完，但检索恢复增益被诚实证伪 | gated **0.2273** vs agentic **0.2727**，一例差距；rule == LLM；judge 未达部署门槛 | `EVALUATION_REPORT.md` Q2、`JUDGE_AGREEMENT_REPORT.md`、`Q2_AGENT_DESIGN.md` |
| Q3 `v2.0-q3-action-governance` | 信任层从“答案”升级到“有副作用的动作” | unauthorized-action blocked **1.00**；F11/F13 **0**；但 anti-gaming triad **False** | `Q3_ACTION_GOVERNANCE_DESIGN.md`、`SPEC_Q3_P8.md`、`FAILURE_ANALYSIS.md` |
| Q4 `v3.0-q4-reliability` | Q3 负结果被机制修复翻成正结果 | held-out `ops_test` 上 precision@authorized **0.4545 -> 0.6471**；over-escalation **0.2857 -> 0.05**；triad **False -> True**；F11/F13 仍 **0** | `Q4_P4_FREEZE.md`、`Q4_P2_PREREGISTER.md`、`EVALUATION_REPORT.md` Q4 |
| Q4 可靠性硬化 | 标准可观测与发布门禁落地 | q4-p5 trace 可导出 OpenInference/OTel span；run manifest；release gates 覆盖 F11/F13/leakage/mock/triad | `SPEC_Q4_P6_P7.md`、`TECHNICAL_DESIGN.md` ADR-016 |
| Q5 protocol-v3 real-dev | Agent loop、安全与效率通过，但 LLM policy binding 未过门 | observation recall **1.00**；Hybrid call/token ratio **0.590909 / 0.644393**；安全 failures **0**；semantic uplift **0.083333**、within/cross **0.166667 / 0.333333**，NOT FREEZE READY | `Q5_P5_REAL_DEV_V3_NEGATIVE_DIAGNOSTIC.md`、`SPEC_Q5_P5_H_POLICY_SEMANTIC_BINDING.md` |

短讲法：

> 我先证明这个 RAG-Agent 不会乱答和乱执行，再诚实证明它在动作选择上不够好；最后没有放松阈值，
> 而是修复真实检测/路由缺陷，让规则控制器在没调过的留出测试集上通过 anti-gaming triad。

------

## 3. 网页端 Demo 交付

项目现在有两个网页入口，定位不同，互相补充。

### 3.1 运行时控制台：`/console/`

路径：`app/web/index.html`，由 FastAPI 挂载到 `/console/`。

用途：展示 Q3/Q4 的“读 -> 判 -> 动 -> 治”真实治理流程。它调用后端治理接口，能看见：

- timeline：检索、条件检测、动作提议、validator、风险路由。
- approval queue：高风险动作进入人工审批。
- audit trail：动作 sink 记录可追溯。
- blocked log：越权或无证据动作被 fail-closed 拦下。

后端接口：

- `POST /govern/run`
- `GET /govern/pending`
- `POST /govern/pending/{record_id}/approve`
- `POST /govern/pending/{record_id}/reject`
- `GET /govern/audit`
- `GET /govern/audit/blocked`

本地运行：

```powershell
python -m uv run uvicorn app.main:app --reload
```

然后打开：

```text
http://127.0.0.1:8000/console/
```

### 3.2 招聘向作品站：`frontend/`

路径：`frontend/`，Astro + Tailwind，snapshot-first，可静态部署。

用途：不是给运维用户操作的控制台，而是给面试官/招聘方看的高级作品 demo。它讲完整 Q1-Q4
项目叙事，并把“看 agent 跑一遍”做成第一屏级别的可视化重点。

已实现页面结构：

- `Hero`：0 假答、0 越权、triad False -> True 的头条数字。
- `Claim`：项目主张，强调“证明哪里不行，再修好”。
- `AgentWalkthrough`：滚动引导式读 -> 判 -> 动 -> 治走查，含越权 fail-closed 高潮。
- `TrajectoryPlayer`：5 个真实轨迹快照的可探索播放器。
- `Pipeline`：治理管线和 OpenInference span 视角。
- `TriadGate`：Q3/Q4 before/after 与“全升级作弊者”对照。
- `TheTurn`：Q3 负结果到 Q4 正结果的转折。
- `Arc`：Q1-Q4 四阶段演进。
- `Honest`：F1-F13 与 Q4 “真但薄”披露。
- `UnderHood`：技术栈、tag、CI 硬门。

数据快照：

- `frontend/src/data/triad.json`
- `frontend/src/data/trajectories.json`
- `frontend/src/data/audit.json`
- `frontend/src/data/arc.json`

本地运行：

```powershell
cd frontend
npm install
npm run dev
```

默认地址：

```text
http://localhost:4321
```

构建静态站：

```powershell
cd frontend
npm run build
```

产物输出到 `frontend/dist/`。

------

## 4. 对外展示顺序

推荐 3 分钟讲法：

1. 打开 `frontend/` showcase：先讲一句话主张和 Q1-Q4 arc。
2. 滚到 `AgentWalkthrough`：展示一个正常动作如何进入人工审批，再展示越权动作如何被 validator 拦下。
3. 滚到 `TriadGate` / `TheTurn`：解释为什么只拦越权不够，Q4 如何把动作选择从 False 翻到 True。
4. 最后打开 README 或 `EVALUATION_REPORT.md`：证明所有数字来自真实 run，不是演示文案。

如果面试官要看“真能跑”：

1. 启动 FastAPI。
2. 打开 `/console/`。
3. 用 `/govern/run` 跑 canned 场景或手动 query。
4. 展示 pending / audit / blocked 记录。

------

## 5. 诚实边界

这些定语不能省：

- Q4 正结果是规则控制器主路径达成；LLM 控制器作为消融并报，held-out 上 triad 仍为 False。
- Q3 -> Q4 before/after 是系统状态演进比较，不是同一数据集 A/B；承重 claim 是 Q4 在留出 test 上 triad=True。
- Q4 结果“真但薄”：precision@authorized 过线约 1 个 case，6/17 authorized 残留错误主要是小语料检索/重排边界。
- `citation_valid=1.00` 是结构有效性，不等于人工证明每条引用语义支持都完美。
- mock smoke、fixture 回归、静态 showcase 快照都不能当 headline 指标。
- `frontend/` 默认 snapshot-first；它展示真实 run 快照。要“实时跑 agent”，使用 `/console/` 或后续接入 live mode。

------

## 6. 当前资料地图

| 读者问题 | 看哪里 |
| --- | --- |
| 5 分钟了解项目值不值得看 | `README.md`、本文 |
| 求职/面试怎么讲 | `PROJECT_OVERVIEW.md`、`INTERVIEW_QA.md`、本文 §4 |
| 真实评测数字从哪来 | `EVALUATION_REPORT.md`、`Q4_P4_FREEZE.md` |
| 失败和边界是什么 | `FAILURE_ANALYSIS.md` |
| 架构为什么这么设计 | `TECHNICAL_DESIGN.md` |
| 网页端 demo 怎么跑 | `frontend/README.md`、本文 §3 |
| 运行时控制台 API 是什么 | `SPEC_Q3_P8.md`、`app/api/govern_routes.py` |
