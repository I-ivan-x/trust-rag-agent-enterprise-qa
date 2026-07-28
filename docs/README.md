# Agent Reliability Lab 文档入口

这里同时保存“当前事实”和“历史研究记录”。如果你是第一次打开仓库，不需要按文件名
从头阅读；按下面的时间预算进入即可。

## 面试官快速路径

| 时间 | 阅读或演示路径 | 能得到什么 |
| --- | --- | --- |
| 30 秒 | [`../README.md`](../README.md) 的项目定位、三项结果与页面截图 | 项目解决什么问题、最重要的正负结果 |
| 90 秒 | 展示页已预启动时，看 Hero → Five Questions → Governed Runtime；依赖安装与启动时间不计入观看预算 | 为什么 Agent 不能越权、五个问题如何串成工程故事 |
| 3 分钟 | [`THREE_MINUTE_DEMO_SCRIPT.md`](THREE_MINUTE_DEMO_SCRIPT.md) | 可直接照读的完整网页演示 |
| 5 分钟 | [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) → [`Q5_FINAL_REPORT.md`](Q5_FINAL_REPORT.md) | 架构、结果转折、Q5 为什么以负结论收口 |
| 验真 | [`Q5_CLAIM_MATRIX.md`](Q5_CLAIM_MATRIX.md) → [`PROJECT_ARCHIVE_AND_MAINTENANCE.md`](PROJECT_ARCHIVE_AND_MAINTENANCE.md) | Claim 来源、适用范围、复现与维护边界 |

## 当前事实入口

这些文档描述当前项目状态，可用于 README、面试和维护：

- [`LATEST_RESULTS_AND_DEMO.md`](LATEST_RESULTS_AND_DEMO.md)：Q1–Q5 当前结果与演示入口。
- [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md)：招聘视角的项目叙事。
- [`INTERVIEW_QA.md`](INTERVIEW_QA.md)：高压追问、AI 协作所有权和未部署边界。
- [`THREE_MINUTE_DEMO_SCRIPT.md`](THREE_MINUTE_DEMO_SCRIPT.md)：180 秒演示动作与话术。
- [`RESUME_BULLETS.md`](RESUME_BULLETS.md)：短版简历句与证据合同。
- [`Q5_FINAL_REPORT.md`](Q5_FINAL_REPORT.md)：生成的 Q5 正式结论。
- [`Q5_CLAIM_MATRIX.md`](Q5_CLAIM_MATRIX.md)：生成的逐 Claim 证据映射。
- [`Q5_BOUNDARY_A_F_SUMMARY.md`](Q5_BOUNDARY_A_F_SUMMARY.md)：Boundary A–F 当前解释。
- [`EVALUATION_REPORT.md`](EVALUATION_REPORT.md)：完整评测历史。
- [`FAILURE_ANALYSIS.md`](FAILURE_ANALYSIS.md)：失败分类、归因与已关闭研究轨。
- [`ENGINEERING_DISCIPLINE.md`](ENGINEERING_DISCIPLINE.md)：交付纪律与 AI 协作边界。
- [`PUBLIC_REPOSITORY_AUDIT.md`](PUBLIC_REPOSITORY_AUDIT.md) 和
  [`DATA_PROVENANCE_AUDIT.md`](DATA_PROVENANCE_AUDIT.md)：公开安全、许可证和数据来源。
- [`PROJECT_ARCHIVE_AND_MAINTENANCE.md`](PROJECT_ARCHIVE_AND_MAINTENANCE.md)：
  封存状态、允许的维护和解冻条件。

数字与状态发生冲突时，以 `data/claims/claim_registry.json`、
`data/releases/release_manifest_v2.json` 和
`data/public_repository/audit_registry_v2.json` 为准。

## 历史研究记录

以下材料保留的是“当时的计划、协议和判断”，其中的 `pending`、下一步或旧品牌不代表
当前仍有未完成工作：

- `SPEC_*.md`、`Q*_DESIGN.md`、`Q*_PREREG*.md`：阶段规格和预注册协议。
- `Q5_P*.md`、`Q5_IMPLEMENTATION_HANDOFF.md`：Q5 开发阶段的诊断与交接。
- `WEEK6_*.md`、`Q1_HARD_DEMO_TASK_PLAN.md`：阶段收口与任务历史。
- `AGENT_RESIDUAL_*_DRAFT.md`、`HARD_NEGATIVE_ADJUDICATION.md`：
  草案和裁定过程；正式结论应回到当前评测报告。
- `TECHNICAL_DESIGN.md`：Q1–Q4 append-only ADR；Q5 架构另见
  [`Q5_ADAPTIVE_AGENT_DESIGN.md`](Q5_ADAPTIVE_AGENT_DESIGN.md) 和正式 Q5 报告。

历史文件不做静默回写，因为它们是研究过程证据。当前状态由本页上方的事实入口覆盖。

## 个人准备材料

[`STUDY_CHECKLIST.md`](STUDY_CHECKLIST.md) 是个人面试学习目录。未勾选项表示尚未自行
确认脱稿掌握度，不代表代码、评测或封存仍未完成，也不应由自动化代替 Owner 勾选。
