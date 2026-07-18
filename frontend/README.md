# Agent Reliability Lab frontend

**Governed Runtime, Evaluation Harness, and Decision Frontier for Tool-Using Agents**

面向中文技术面试的静态 Astro 展示页，以一条公开安全的虚构发布事故串联受治理运行时、
评测基础设施与 Q5 决策边界。TrustRAG 只作为复现实验中的 legacy codename（历史代号）保留。

## Development

Node.js `>=22.19.0` and npm `>=10.9.0` are required. CI and `.nvmrc` use Node
22.19.0. The site remains a static Astro build: no SSR, server islands, remote
image service, or runtime model/provider call.

```bash
cd frontend
npm ci
npm run dev
npm run build
npm run test:e2e
```

Dependency audit details and the remaining Lighthouse-only moderate advisory are
recorded in [`DEPENDENCY_SECURITY.md`](./DEPENDENCY_SECURITY.md).

## Public data

The Q1–Q5 narrative is generated from `data/claims/claim_registry.json`:

- `src/data/questions.json`
- `src/data/headline-results.json`
- `src/data/decision-frontier.json`
- `src/data/q5-evidence.json`
- `src/data/engineering-signals.json`
- `src/data/presentation-zh-cn.json`

Rebuild and verify them from the repository root:

```bash
python scripts/build_public_claims.py
python scripts/build_public_claims.py --check
python scripts/check_claim_drift.py
```

中文 Claim 标签、范围、限制、摘要模板和指标名称的单一数据源是
`data/claims/presentation_zh_cn_v1.json`。前端只读取生成后的 presentation，不按
`claim_id` 重写结论。

默认事故故事来自 `data/showcase/interview-v1/`，固定为 `synthetic`、
`demonstration_only`、`headline_eligible=false` 和请求数为零。它不会进入正式
Claim 或评测来源：

```bash
python scripts/verify_showcase_isolation.py
python scripts/build_interview_showcase.py --check
```

旧的 control-room snapshot 仍作为既有 Q4 复现输入保留，但默认面试故事读取
`src/data/interview-showcase.json`。该文件由隔离的 synthetic corpus 确定性生成。
历史 snapshot 仍可用原有命令校验：

```bash
python scripts/build_control_room_snapshot.py
python scripts/build_control_room_snapshot.py --check
```

`scripts/build_showcase_snapshots.py` remains only as the historical Q4 source
reproducer. The public page does not read `trajectories.json` directly.

## Information architecture

The page contains exactly seven major sections:

1. Hero
2. Five Questions
3. Governed Runtime
4. Reliability Turn
5. Q5 Decision Frontier
6. Evaluation Infrastructure
7. Evidence Ledger

`AgentControlRoom` composes the compact `Pipeline` and `TrajectoryPlayer`.
`DecisionFrontier` 默认解释规则、开放语义和高风险三条路径，研究缩写折叠到技术详情。
`EvidenceLedger` 展开所有正结果、负结果、未评估结论和来源血缘。

## Frontend acceptance

Playwright covers 1440×900, 1280×720, and 390×844. Layout measurement and local
screenshots are produced by:

```bash
node scripts/measure-layout.mjs <url> <commit> [output.json] [width] [height]
node scripts/capture-viewports.mjs <url> [output-directory]
```

The acceptance subset checks the seven-section contract, Q5 position, overflow,
keyboard/focus behavior, reduced motion, no-JavaScript conclusions, interview
narrative, corpus isolation, and claim reverse linkage. After an implementation
commit, `npm run test:closure-acceptance` performs three consecutive Lighthouse
runs and writes the compact receipt plus three viewport screenshots.
