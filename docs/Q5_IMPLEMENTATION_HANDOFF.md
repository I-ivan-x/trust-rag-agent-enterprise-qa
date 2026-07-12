# Q5 Implementation Window Handoff

版本：v2
日期：2026-07-10；同步：2026-07-12
用途：新窗口的唯一执行入口

------

## 1. 双窗口职责

### plan/spec/diagnostic/report/tag 窗口（本窗口）

- 拥有 Q5 问题定义、成功门、数据协议和解释权；
- 编写/冻结 Q5 docs；
- 编写正式 q5_dev/q5_test protocol、case 和 gold；
- 审查 implementation packet；
- 决定是否允许 dev/real run；
- 最终更新报告、README、showcase 和 tag。

### implementation/real-run 窗口（新窗口）

- 只按 frozen spec 修改代码、测试、CI 和 fixture；
- 不修改成功阈值、Q5 设计、正式 gold、README headline 或历史报告；
- 每批完成后提交代码并回传机械证据；
- 只有收到 plan/report 窗口明确 run authorization 后，才可调用真实 provider；
- real run 后只返回原始 artifacts，不先写叙事结论。

若两个窗口并行写同一仓库，必须使用独立 git worktree；否则严格串行，一次只允许一个窗口写文件。

------

## 2. 新窗口启动指令

将以下内容作为新窗口首条任务：

```text
你是 Q5 implementation/real-run 单代码执行窗口。

先完整阅读：
1. docs/Q5_P0_DIAGNOSTIC.md
2. docs/Q5_ADAPTIVE_AGENT_DESIGN.md
3. docs/SPEC_Q5_P1_P2.md
4. docs/SPEC_Q5_P3_P4.md
5. docs/Q5_IMPLEMENTATION_HANDOFF.md

边界：
- 不修改上述 Q5 docs、ROADMAP、README、EVALUATION_REPORT、FAILURE_ANALYSIS；
- 不修改 Q5 Gate 数值；
- 不创建正式 q5_test；
- 未获授权不得 real run；
- 不重写 Q1-Q4 frozen runner/validator 行为；
- 发现 spec 冲突时停止并回报，不自行改设计。

先执行 Batch 0，仅做 baseline hygiene：修 Ruff、pytest marker/warnings 中可局部修项、
新增 GitHub Actions lint/test/frontend build/release-gate fixture。全绿并提交后停止，回报 commit SHA、
测试输出和未处理 warning。不要直接进入 Q5-P1/P2。
```

------

## 3. 执行批次

| Batch | 内容 | 完成后动作 |
| --- | --- | --- |
| 0 | baseline hygiene + real CI wiring | commit，停止，回报 |
| 1 | Q5-P1 task/gold/environment contract | commit，停止，回报 |
| 2 | Q5-P2 authorized DecisionContext + leakage tests | commit，停止，回报 |
| 3 | Q5-P3 tools/router/policies/bounded loop | commit，停止，回报 |
| 4 | Q5-P4 outcome metrics/harness/gates | commit，停止，回报 |
| 5 | q5_dev diagnostic/mock or approved real dev run | artifacts，停止，回报 |
| 6 | freeze 后 q5_test one-shot real run | artifacts only，停止，回报 |

不得把多个 batch 合成一个大提交。每批 review 通过后才进入下一批。

### 当前交接状态（2026-07-12）

- Batch 0-4、5-C1、5-C1R 已完成并通过 plan/report 审核；
- protocol-v1 历史 artifact 由冻结 verifier 复算，活动协议为 protocol-v2；
- 正式 q5_dev v2 由 plan/report 窗口 author，v1 数据归档在 `data/q5/archive/dev-v1/`；
- 有效预注册修订为 `Q5_P5_PREREG_AMENDMENT_V2.md`；
- synthetic k=3 已证明质量、观察与安全路径成立，但 G3 token ratio 为 `0.65233`，高于冻结上限 `0.65`；
- 下一动作仅为 Batch 5-C3：压缩由同一 Pydantic validator 导出的 prompt tool schema 表示，随后重跑 synthetic k=3；
- 只有 synthetic G3 通过且 plan/report 复核后，才批准完整 q5_dev v2 primary real run；
- q5_test、confirmatory run、freeze 和 tag 继续锁定。

------

## 4. 每批回报格式

```text
Batch:
Commit SHA:
Files changed:
Acceptance items passed:
Commands + exact result:
Q1-Q4 regression status:
LLM calls / real token usage:
Known deviations:
Open blockers:
Worktree status:
```

不要只说“测试通过”；必须给 passed/skipped/warnings 和 lint/frontend build 结果。

------

## 5. 禁止事项

- 禁止从 `gold_action` 推导 requested capability；
- 禁止将 q5 stratum 传给 router；
- 禁止把 blocked chunk text 放进 context/prompt/trace；
- 禁止为达 G1 调低 0.10 uplift 或更改 bootstrap 门；
- 禁止为减少调用量把 LLM-only 做成弱 baseline；
- 禁止在 q5_test 后修同一 freeze 的代码；
- 禁止改写 Q2-Q4 的 rule≈LLM 负结果；
- 禁止未授权 push/tag/release。

------

## 6. Plan 窗口回收物

implementation 窗口每批返回后，本窗口负责：

1. 读 diff 和测试证据；
2. 对照 spec 标 accepted / rejected / deviation；
3. 更新 Q5 ROADMAP 状态；
4. 决定下一批是否解锁；
5. dev/test run 后独立解释结果；
6. 所有 Gate 通过后才写 release narrative 和 tag。
