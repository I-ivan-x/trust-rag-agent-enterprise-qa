# TrustRAG Showcase — 前端作品 demo 规划（planning, not built yet）

版本：v0-plan
状态：规划稿，待 Owner 拍板关键岔路（§9）后再开工。
目标读者：招聘方 / 面试官（非运维用户）。这是**作品展示站**，不是 Q3 那个运行时控制台。
前端用 `ui-ux-pro-max-skill`（Claude 侧驱动其设计系统生成器）。

------

## 1. 目标与定位

```text
Q3 的 /console 是"功能性运维控制台"（读→判→动→治 + 待审/审计/拦截），是工具 demo——Owner 不满意：
  朴素、只覆盖 Q3 一个切片、没讲整条叙事。
新 showcase = 面向招聘的【高级交互作品站】，讲完整 Q1–Q4 叙事，可独立部署、随时打开就能看。
一句话主张（hero）：把 agent 做成【可测、可审、可回归、且敢于诚实证明自己哪里不行、再把它修好】的工程系统。
```

## 2. 必须传达的核心叙事 + "wow 时刻"

| # | 叙事支柱 | 展示形式（wow） |
| --- | --- | --- |
| A | 一句话定位 + 头条数字 | Hero：0 假答 · 0 越权动作 · triad False→True（动态计数 + 真实 run_id 标注） |
| B | **动作治理（agent 味）** | **交互式「读→判→动→治」轨迹播放器**：选一个场景，逐步播放 检索→条件→拟议动作→validator/路由，**越权被拦那一帧高亮**（核心看点） |
| C | **反作弊 eval** | anti-gaming triad 仪表盘：Q3(False)→Q4(True) before/after；一个"全升级作弊者会得几分"对照开关，演示**门确实能拦造假** |
| D | **fail-closed 安全证据** | 审计链 + 越权拦截日志（real snapshot），F11/F13=0 徽章 |
| E | **诚实工程**（差异化） | Q1→Q4 arc 时间线 + 失败分类法 F1–F13，把"负结果→根因→修复"做成可展开卡片；Q4"真但薄"如实标 |
| F | 架构可信 | 读→判→动→治 管线图 + OpenInference span kind 映射（retriever/reranker/guardrail/agent/tool） |

> **诚实约束（不可违反）**：showcase 必须保留项目 DNA——负结果、Q4"真但薄"定语、两次 run、小语料边界都要可见。
> 一个只摆 win 的作品站会**背叛**整个反自欺主题；把"诚实"做成一等公民反而是这个 showcase 的差异化。

## 3. 信息架构（单页滚动 + 锚点导航；或多路由）

```text
Hero（主张 + 头条数字 + "看 agent 跑一遍"CTA）
└ The Arc（Q1→Q4 时间线，每季一卡：主张 / 实测数字 / tag）
└ Live Agent（B：读→判→动→治 轨迹播放器，5 个 canned 场景含越权）
└ Trust by Design（D+F：管线图 + 四道 gate + 审计/拦截 snapshot + F11/F13=0）
└ The Anti-Gaming Gate（C：triad before→after + 作弊者对照）
└ Honest Engineering（E：F1–F13 可展开 + 负→正故事 + 披露）
└ Under the Hood（栈 / 364 测试 / 4 tag / OpenInference·OTel·CI 门）
└ Footer（GitHub、各 tag、简历 bullet 链接）
```

## 4. 数据策略（关键架构决定）

```text
Snapshot-first（默认，保证独立部署随时可看）：
  把真实 run 数据烘焙成前端静态 JSON——q4-p5 summary（triad/指标 before→after）、
  几条真实轨迹（读→判→动→治，含越权案）、审计/拦截记录。全部标 run_id + "real run"，不杜撰。
Live mode（可选开关）：配置后端 URL 时，"看 agent 跑一遍"调真实 /govern/run；默认走 snapshot 回放。
  → 部署到静态托管也 100% 可用；本地起后端则能真跑。
```

## 5. 技术与风格

```text
风格（经 skill 设计系统生成，但我会显式排除 cyberpunk/霓虹/gaming，指定"enterprise/trust/governance,
  premium dark technical, sober, WCAG AA"）：精致暗色 + 克制单一强调色 + 等宽字体用于数据 +
  bento/feature-grid 分区 + 轻动效（滚动渐入、轨迹步进、计数器）。参考气质：Linear / Vercel / Datadog。
栈（推荐 Astro + Tailwind + 轻量岛屿）：内容为主、按需交互岛、可静态部署；轨迹播放器/仪表盘做成岛。
  备选：Next.js（全 React，交互多时更顺）/ 纯 html-tailwind（最轻，但"高级+完整"会受限）。
目录：新建 `frontend/`（与 Q3 `app/web/` 运行时控制台并存，互不污染）。
```

## 6. 与现有 Q3 控制台的关系

```text
保留 Q3 /console 作为"真实运行时控制台"（已接 API、已测）；showcase 的 Live mode 可链接/内嵌它。
showcase = 对外作品门面；/console = 里子功能件。二者分工，不重复造、不互相删。
（若 Owner 想直接取代 Q3 控制台，也可——但建议并存：一个讲故事、一个证明真能跑。）
```

## 7. 分期（小项目拆解）

```text
P0  本规划 + Owner 拍板 §9 岔路
P1  数据快照 + 文案：从真实 run 抽 q4-p5/轨迹/审计 JSON；写各区英文文案；skill 出设计系统（暗色 premium）
P2  静态骨架：Hero + Arc 时间线 + 架构图 + 结果仪表盘（读 snapshot）
P3  交互轨迹播放器（读→判→动→治 回放 + 越权高亮；live mode 可选）
P4  anti-gaming triad 仪表盘（before→after + 作弊者对照）+ 审计/拦截视图
P5  打磨（动效/响应式/无障碍/性能）+ 部署（静态托管）+ README 链接
```

## 8. 工作量与执行

```text
体量：比 Q3 控制台大不少（多区叙事站 + 2-3 个交互岛 + 设计系统）。约相当于 P1–P5 分多次。
执行：前端用 skill 由 Claude 做；数据快照抽取/任何后端适配（如 live mode 的 CORS/只读端点）走 Codex。
不碰：validator/阈值/已冻结 run 数字/Q1–Q4 结论——showcase 只读、只展示，不改后端逻辑。
```

## 9. 关键岔路（Owner 已拍板，锁定）

```text
D1 栈        = Astro + Tailwind + 轻量岛   ✅
D2 数据      = Snapshot-first + 可选 live mode   ✅
D3 Q3 控制台 = 并存（showcase 对外门面；/console 真运行时件，live mode 链接它）   ✅
D4 部署      = 静态托管（默认 Vercel/Netlify/Pages；亦可 FastAPI 挂 /showcase）；P5 确认   〔默认〕
D5 语言      = 纯中文界面   ✅
```

## 10. P1 详规（锁定后第一阶段，可直接开工）

目录：新建 `frontend/`（Astro 项目；与 `app/web/` 并存）。

### 10.1 数据快照抽取（Codex 或 Claude；从真实 run 落静态 JSON 到 `frontend/src/data/`）

```text
triad.json      ← q3-p7 与 q4-p5 summary：两系统 precision@authorized / over_escalation /
                  escalation_when_insufficient / unauthorized_blocked / F11 / F13 / triad / pass^k
                  （before→after；含 run_id；外加"全升级作弊者"对照值，可由 governor 对 escalate-all 跑一遍得）
trajectories.json ← q4-p5 traces.jsonl 选 ~5 条代表案（flag_stale / open_ticket / send_alert /
                  越权→escalate / no_op），每条含 读(检索 chunk)→判(conditions+授权)→动(拟议+控制器)→
                  治(validator+风险层+approval_state) 各步字段
audit.json      ← 演示 sink 记录（tickets/alerts/annotations/escalations）+ 越权拦截子集
arc.json        ← Q1–Q4 每季：主张 / 实测数字 / tag / 关联失败码（F1–F13）
全部标 "real run + run_id"，不杜撰；Q4 "真但薄"定语写进 arc.json 的 Q4 卡片。
```

### 10.2 设计系统（Claude 驱动 skill；显式排除霓虹/gaming）

```text
python .../search.py "enterprise trust & governance dev-tools product showcase, premium dark technical,
  sober, restrained single accent, monospace for data/metrics, WCAG AA, NOT cyberpunk/neon/gaming"
  --design-system --stack html-tailwind -p "TrustRAG Showcase"
→ 取其色板/字体/间距/动效为 Astro+Tailwind 的 design tokens；若仍推 gaming 配色，按 Q3 经验手动改为
  精致暗色（深 slate 底 + 单一克制强调色 + 等宽数字）。
```

### 10.3 P1 交付物

```text
[ ] frontend/ Astro 脚手架 + Tailwind + design tokens（暗色 premium）
[ ] frontend/src/data/{triad,trajectories,audit,arc}.json（真实 run 快照）
[ ] 中文文案大纲（§3 各区）落 frontend/src/content/
[ ] Hero 区 + Arc 时间线区静态成型（读 arc.json），本地 `astro dev` 可看
```

## 11. 执行分工

```text
Claude（前端 + 设计 + 文案，用 skill）：Astro 站、各区、交互岛、中文文案、design tokens。
Codex（数据 + 后端适配）：§10.1 快照抽取脚本；live mode 若需后端只读/CORS 适配（默认不需，snapshot 优先）。
不碰：validator/阈值/已冻结 run 数字/Q1–Q4 结论——showcase 只读、只展示。
诚实约束（§2 末）贯穿全程。
```
