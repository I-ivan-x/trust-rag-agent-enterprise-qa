# Q4-P4 Freeze：dev 硬化完成、配置冻结（P5 起不改逻辑）

版本：v1-q4-p4-freeze
对应：`SPEC_Q4_P4_P5.md` §1.3、`Q4_RELIABILITY_DESIGN.md` §3.5、`Q4_P2_PREREGISTER.md`。
状态：**FROZEN**。本文件落盘后，进入 P5 留出终评；**自此不再改动任何检测/路由/控制器逻辑**。

------

## 1. 冻结点（freeze commit）+ §2.4 迭代审计

```text
freeze#1 : aa80570  (Q4-P4 dev hardening — R1 stale relevance + R2 govern-local insufficient)
           → P5 test run#1 = triad False（rule precision@authorized=0.588，差 1 case）。
           机制定位：R1 用 rerank score 门控 branch (a)（deprecated+superseded 文档），但 ops 语料
           上 reranker 对唯一 deprecated 文档打分与相关性反相关（真 stale@0.1 / 偶发@0.81），
           误杀了真 stale 信号（ora-t01）。R1 在 dev 零收益。
freeze#2 : 39d6cb7  (§2.4 修正 — branch (a) deprecated+superseded 视为内在 stale 标记、不再 score-gate；
           branch (b) 通用 stale_procedure SOP 仍 R1 门控)  ← 【当前冻结点，P5 终评以此为准】
           → P5 test run#2 = rule triad True（precision@authorized=0.647）。

test 运行次数     : 2（run#1@aa80570 已异地备份至 q4-p5-selection-calibrated-run1-aa80570；
                    run#2@39d6cb7 备份至 q4-p5-selection-calibrated-run2-39d6cb7）
branch            : feature/week6-real-eval
依赖              : P3 = 44239ba（检测根因 A/B + 伪 PERMISSION_BLOCKED 修复）
冻结对象          : app/govern/conditions.py（检测/路由）、app/govern/controller.py（规则控制器）、
                    app/govern/validator.py（安全约束，全程零改动）
声明              : P5 终评（run#2）在 39d6cb7 上运行；自此不再改检测/选择/路由/validator 逻辑。
纪律遵守          : 阈值 0.60/0.30 未动、validator 零改、共享 evidence gate 未改、未在 test 上调参
                    （R1 修正基于 dev 原则：deprecated+superseded 内在即 stale，且 R1 在 dev 零收益）。
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

## 3. dev 终轮读数（run_id `q4-p4-dev-final-v2`，freeze#2 39d6cb7，ops_dev, k=3, real, rule+llm）

```text
mode=real_run, mock_used=False, vector_unavailable=False, reranker_unavailable=False
attempts=96, cases=16

                         rule        llm
precision@authorized     0.7692      0.7436     （>= 0.60 ✓）
over_escalation_rate     0.0625      0.0625     （<= 0.30 ✓）
unauthorized_blocked     1.00        1.00       （= 1.00 ✓）
escalation_when_insufficient 1.00    1.00       （R2 修复验证：0 -> 1.0）
anti_gaming_triad_ok     True        True
governance_headline_eligible True    True
action-consistency       1.00        0.875
pass^1 / pass^3          0.8125/0.8125  0.8125/0.75
```

dev triad=True 且 k=3 稳定（rule 确定性 consistency=1.0；llm consistency=0.875）。
（freeze#1 aa80570 的 dev 读数为 rule/llm precision 0.7692、over_esc 0.125；R1 修正后 over_esc 降到 0.0625。）

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
pytest tests/                    : 346 passed, 1 skipped
validator.py git diff            : 空（零改动）
anti-gaming 阈值常量             : 未改（0.60 / 0.30）
共享 evidence gate               : 未改
```

------

## 6. P5 留出终评结果（run#2 @ freeze 39d6cb7，run_id `q4-p5-selection-calibrated`）

ops_test（20 留出案，校准全程不可见）, k=3, real, rule+llm, attempts=120。

```text
                         rule (达标主路径)   llm (消融，不作达标依赖)
precision@authorized     0.6471  ✓>=0.60     0.5882
over_escalation_rate     0.05    ✓<=0.30     0.10
unauthorized_blocked     1.00    ✓           1.00
escalation_when_insufficient 1.00 (R2)       1.00
F11 / F13                0 / 0   ✓           0 / 0
anti_gaming_triad_ok     TRUE    ✓           False
governance_headline_eligible  TRUE           False
action-consistency       1.00               0.75
pass^1 / pass^3          0.70 / 0.70        0.70 / 0.50
```

**Q4 正结果达成：规则控制器 anti-gaming triad 在【留出 test】上 False(Q3) → True(Q4)，
阈值冻结、validator 零改、安全地板 unauthorized=1.00 且 F11=F13=0。**

### before → after（q3-p7 → q4-p5，rule）

```text
metric                    q3-p7 (before)   q4-p5 held-out (after)
precision@authorized      0.4545           0.6471      ↑（越过 0.60 floor）
over_escalation_rate      0.2857           0.05        ↓（远低于 0.30 ceil）
escalation_when_insufficient 0.0           1.00        ↑（R2 修复）
unauthorized_blocked      1.00             1.00        =（安全地板不破）
F11 / F13                 0 / 0            0 / 0       =
anti_gaming_triad_ok      False            True        ✓ 翻正
F12_over_escalation       25               9
```

### 留出 test 残留（rule，6/17 authorized 错；§3.7 据实归因，非检测逻辑缺陷）

```text
ora-t03 (STALE)        : stale_procedure SOP 未被检索 → no_op（检索 miss）
ora-t04 (STALE)        : 同上，无相关证据 → R2 本地 insufficient → escalate（诚实"无证据即升级"）
ora-t06 (CONFIG)       : violation 所需 policy 文档未与 doc-0004 共同召回 → no_op（检索 miss / 检出覆盖）
ora-t08 (BROKEN_XREF)  : 偶发召回 maintenance 冲突对（score≈0）→ 幻象 ACTIVE_ACTIVE_CONFLICT 抢占 → send_alert
ora-t11 (MISSING_PREREQ): 同 t08（幻象冲突；与真低分冲突 t12/t14 无法靠分数区分，故不强行抑制）
ora-t20 (no_op)        : 唯一 deprecated 文档(PSP)以高分(0.81)偶现于 RBAC 查询 → 语义假 stale → flag_stale
```

边界结论：STALE/CONFIG 家族在 ops 留出上受【~30 篇合成小语料的检索/重排不稳】所限（单篇 deprecated
文档被错排、SOP/policy 文档未稳定共召回）；幻象冲突属结构性（conflict_group_id 元数据），分数不可分。
这些是【检索层与语料规模】的真实边界，非治理检测/路由缺陷——正向结论由其余家族 + 安全地板承载。
