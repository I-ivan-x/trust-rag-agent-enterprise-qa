# Agent Reliability Lab (frontend)

**Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents**

招聘向静态作品站，讲完整 Q1–Q5 叙事。TrustRAG 是项目的 legacy codename；内部 run ID、
release tag、artifact schema 和 package identifier 为保持可复现性不迁移。站点使用 Astro + Tailwind，
保持 **snapshot-first**，中文界面。

项目总整理见仓库根的 `docs/LATEST_RESULTS_AND_DEMO.md`。运行时控制台仍由 FastAPI 挂在
`/console/`；本目录是对外展示用的静态 showcase。

## 开发

要求 Node.js `>=22.19.0`、npm `>=10.9.0`；CI 与 `.nvmrc` 固定到 Node 22.19.0。
前端保持纯静态 Astro 输出，Tailwind 4 通过官方 Vite plugin 构建，不启用 SSR、server
islands 或远程图片服务。依赖审计基线与剩余 moderate 的可达性分析见
[`DEPENDENCY_SECURITY.md`](./DEPENDENCY_SECURITY.md)。

```bash
cd frontend
npm install
npm run dev      # http://localhost:4321
npm run build    # 输出静态站到 frontend/dist
npm run preview  # 本地预览构建产物
```

## 数据与公开 claim

Q1–Q5 的当前招聘叙事由根目录 `data/claims/claim_registry.json` 单源生成：

- `src/data/questions.json`
- `src/data/headline-results.json`
- `src/data/decision-frontier.json`
- `src/data/q5-evidence.json`
- `src/data/engineering-signals.json`

每条记录都携带 `claim_id`、source artifact、SHA-256、run ID、execution commit、
artifact commit、evidence mode、scope 和 headline eligibility。修改 registry 后运行：

```bash
python scripts/build_public_claims.py
python scripts/check_claim_drift.py
```

以下旧页面快照继续支持既有 Q1–Q4 组件：

`src/data/{triad,trajectories,audit,arc}.json` 由仓库根的脚本从真实 run 生成：

```bash
python scripts/build_showcase_snapshots.py     # 读 q3-p7 / q4-p5 等真实 run → 写 src/data/*.json
```

旧快照数字标注 run_id；唯一的派生值是「全升级作弊者」的 triad（由留出 test gold 解析计算，
标 `mode: "analytic"`）。before/after 是 Q3→Q4 状态比较（跨演进集），非同集 A/B——承重 claim 是
after 留出集上 triad=True。

## 章节

`Hero` 头条数字 · `Arc` 四季时间线 · `TrajectoryPlayer` 读→判→动→治 交互轨迹（含越权 fail-closed） ·
`Pipeline` 管线图 + OpenInference span · `TriadGate` 反作弊门 + 作弊者对照 · `Honest` F1–F13 + 披露 ·
`UnderHood` 栈/tag/CI 硬门。Q5 的 public-truth 数据合同已经生成，但本批不重构展示组件。

## 部署

静态托管即可（Vercel / Netlify / GitHub Pages）：构建 `npm run build`，发布 `dist/`。

**可选 live mode**（默认走 snapshot 回放）：若要「看 agent 跑一遍」调真实后端，起 FastAPI
（`uvicorn app.main:app`）并把 `TrajectoryPlayer` 的数据源指向 `/govern/run`——后续阶段接入，
当前为 snapshot 回放，保证独立部署 100% 可用。
