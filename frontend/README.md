# TrustRAG Showcase (frontend)

招聘向高级作品站，讲完整 Q1–Q4 叙事。Astro + Tailwind，**snapshot-first**（数据来自真实 run，
独立部署随时可看），暗色 premium 技术风。中文界面。

## 开发

```bash
cd frontend
npm install
npm run dev      # http://localhost:4321
npm run build    # 输出静态站到 frontend/dist
npm run preview  # 本地预览构建产物
```

## 数据快照（真实 run，可复现）

`src/data/{triad,trajectories,audit,arc}.json` 由仓库根的脚本从真实 run 生成：

```bash
python scripts/build_showcase_snapshots.py     # 读 q3-p7 / q4-p5 等真实 run → 写 src/data/*.json
```

所有数字标注 run_id；唯一的派生值是「全升级作弊者」的 triad（由留出 test gold 解析计算，
标 `mode: "analytic"`）。before/after 是 Q3→Q4 状态比较（跨演进集），非同集 A/B——承重 claim 是
after 留出集上 triad=True。

## 章节

`Hero` 头条数字 · `Arc` 四季时间线 · `TrajectoryPlayer` 读→判→动→治 交互轨迹（含越权 fail-closed） ·
`Pipeline` 管线图 + OpenInference span · `TriadGate` 反作弊门 + 作弊者对照 · `Honest` F1–F13 + 披露 ·
`UnderHood` 栈/tag/CI 硬门。

## 部署

静态托管即可（Vercel / Netlify / GitHub Pages）：构建 `npm run build`，发布 `dist/`。

**可选 live mode**（默认走 snapshot 回放）：若要「看 agent 跑一遍」调真实后端，起 FastAPI
（`uvicorn app.main:app`）并把 `TrajectoryPlayer` 的数据源指向 `/govern/run`——后续阶段接入，
当前为 snapshot 回放，保证独立部署 100% 可用。
