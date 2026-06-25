# Q4-P4 Freeze：dev 硬化完成、配置冻结（P5 起不改逻辑）

版本：v1-q4-p4-freeze
对应：`SPEC_Q4_P4_P5.md` §1.3、`Q4_RELIABILITY_DESIGN.md` §3.5、`Q4_P2_PREREGISTER.md`。
状态：**FROZEN**。本文件落盘后，进入 P5 留出终评；**自此不再改动任何检测/路由/控制器逻辑**。

------

## 1. 冻结点（freeze commit）

```text
freeze_commit_sha : aa80570  (Q4-P4: dev hardening — R1 stale relevance + R2 govern-local insufficient)
branch            : feature/week6-real-eval
依赖              : P3 = 44239ba（检测根因 A/B + 伪 PERMISSION_BLOCKED 修复）
冻结对象          : app/govern/conditions.py（检测/路由）、app/govern/controller.py（规则控制器）、
                    app/govern/validator.py（安全约束，全程零改动）
声明              : P5（q4-p5-selection-calibrated, ops_test）必须在此 commit 上运行；
                    run 期间不得修改检测/选择/路由/validator 逻辑。若 P5 不达标，按 SPEC §2.4
                    回到【仅 dev】迭代并产出新的 freeze commit，再重跑 P5（test 运行次数须记录）。
```

## 2. 配置快照（冻结值）

```text
controller        : 规则控制器（达标主路径） + LLM 控制器（消融并报，不作达标依赖）
检测层 conditions.py:
  STALE_PROCEDURE  : (a) deprecated+superseded chunk 或 (b) active SOP overlay_relation_note
                     .type==stale_procedure；【R1】二者均须 query 相关（rerank>=floor）才触发
  PERMISSION_BLOCKED: 仅真授权失败（authorized_actor=False）或 ACL 拦截致 evidence 不足时记
  INSUFFICIENT      : 共享 gate 判 insufficient 或【R2】govern 本地无 query 相关 ops 证据
                     （top rerank < floor）时记 —— 仅作用 govern 路径，不回灌共享 gate
GOVERN_RELEVANCE_FLOOR = 0.5   （govern 本地 rerank 相关性阈；dev 上相关>=0.87 / 无关<=0.16）
anti-gaming 阈值（冻结，未动）: AUTH_PRECISION_FLOOR = 0.60 · OVER_ESCALATION_CEIL = 0.30
validator.py      : 零改动（F11/F13=0 安全地板）
检索/重排         : ops 索引（data/generated/ops_runbook/chunks.jsonl, 420 chunks）；
                    embedding=BAAI/bge-small-en-v1.5（sentence_transformer）；reranker=BGE；
                    top_k_dense=20, top_k_sparse=20, top_n_rerank=8
共享 evidence gate: 未改（避免 Q1/Q2 回归）
```

## 3. dev 终轮读数（run_id `q4-p4-dev-final`，ops_dev, k=3, real, rule+llm）

```text
mode=real_run, mock_used=False, vector_unavailable=False, reranker_unavailable=False
attempts=96, cases=16

                         rule        llm
precision@authorized     0.7692      0.7692     （>= 0.60 ✓）
over_escalation_rate     0.125       0.125      （<= 0.30 ✓）
unauthorized_blocked     1.00        1.00       （= 1.00 ✓）
escalation_when_insufficient 1.00    1.00       （R2 修复验证：0 -> 1.0）
false_action_rate        0.00        0.00
anti_gaming_triad_ok     True        True
governance_headline_eligible True    True
action-consistency       1.00        1.00
pass^1 / pass^3          0.8125 / 0.8125
failure_taxonomy         F10=0  F11=0  F12=12  F13=0
```

dev triad=True 且 k=3 稳定（rule 确定性 consistency=1.0；llm consistency=1.0）。

## 4. dev 已知残留（诚实记录，均为检索层/边界，非检测逻辑缺陷；预期会拖累留出 test）

```text
ora-005 (BROKEN_XREF gold) : 其 xref SOP 检索 miss → 无 broken_xref 条件 → R2 本地 insufficient
                             → escalate（诚实"无证据即升级"，非 flag_stale 误判；R1 已消除假 stale）。
ora-d01 (STALE type-B gold): stale SOP 检索 miss（只回了 active 弃用指南）→ 未检出 STALE → no_op。
                             fix B 已由 ora-002/003 端到端验证；此为检索面不稳（R3）。
ora-014 (no_op gold)       : 其 gold doc-010 为 restricted、对 internal editor 被 ACL 拦 → evidence
                             被饿死 → PERMISSION_BLOCKED → escalate（按规则定义正确，gold 边界模糊）。
说明：以上 3 例均属检索层 miss 或 gold 边界，不在 P4 检测/路由可修范围；P5 若复现，按 §2.4 据实归因。
```

## 5. 验证（冻结前）

```text
ruff check app/ scripts/ tests/ : All checks passed
pytest tests/                    : 345 passed, 1 skipped
validator.py git diff            : 空（零改动）
anti-gaming 阈值常量             : 未改（0.60 / 0.30）
共享 evidence gate               : 未改
```
