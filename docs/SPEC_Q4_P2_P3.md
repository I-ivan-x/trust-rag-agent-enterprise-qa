# SPEC Q4-P2 + P3：评测集扩容/留出 + 检测修复/路由校准

版本：v1-q4-p2p3-impl
状态：实现规格（freeze-ready）。依赖 Q4-P1 诊断（`8400a45`，真实向量验证）。
对应：`Q4_RELIABILITY_DESIGN.md` §3.2（扩容/留出）/ §3.3（检测）/ §3.4（路由）/ §3.6（Gate）。
分工：Owner（留出 test gold 终标 + 预注册签字）/ Codex（扩容工具 + 检测/路由修复 + 单测）。
**铁律（全程不可碰）**：validator 安全约束不动、anti-gaming 阈值（0.60/0.30）冻结、test 集校准期不可见。

------

## 0. P1 已定死的根因（本 SPEC 据此精确施工）

```text
flag_stale 死路 = 100% 检测漏（3/3），evidence 全 sufficient（非 insufficient 短路），routing_error=0：
  根因 A：overlay 的 superseded_by 在 ingest 丢失 → chunk.superseded_by=None，
          而 stale 规则要 status==deprecated AND superseded_by → 永远 False（ora-001 死法）。
  根因 B：检测规则不读 overlay_relation_note.type=="stale_procedure"；ora-002/003 的 gold 文档
          里没有 deprecated 文档，stale 信号纯靠 active SOP 交叉引用 → 现规则无论检索多准都不触发。
过度升级 4 例（ora-002/003/005/014）= 伪 PERMISSION_BLOCKED：授权 actor（authorized_actor=True）
  因【无关】restricted 邻居 chunk 被 ACL 拦，detect 仍记 permission_blocked，控制器最高优先级短路 escalate。
镜像 bug ora-012：唯一真·证据不足案被 evidence gate 误判 sufficient → 漏升级。
```

------

## 1. Q4-P2：评测集扩容 + dev/test 留出 + 预注册

### 1.1 扩容（Owner 出题 + Codex 工具）

```text
现 ops_runbook_action_v1 = 14（已被 P7/P1 见过，全部归 dev）。
新增 ~22 条 → 总 ~36：每个 condition 家族（stale / config / conflict / xref / permission / insufficient）各 ≥5，
  越权子集 ≥6，no_op ≥4。新增 stale case 要同时覆盖两类：
    (a) 含 deprecated+superseded_by 文档（验根因 A 修复）；
    (b) 纯 active SOP 交叉引用、无 deprecated 文档（验根因 B 修复，ora-002/003 同型）。
语料：复用 data/ops_runbook_corpus/，按需补 seeded sop-/policy- 片段（metadata_origin=seeded_overlay，声明合成）。
```

### 1.2 dev/test 物理隔离（防过拟合的根）

```text
dev 集（校准可见）  ≈ 16：原 14 + 2 新 → data/gold_eval/ops_runbook_action_v1_dev.jsonl
test 集（冻结留出）≈ 20：新增 → data/gold_eval/ops_runbook_action_v1_test.jsonl
纪律：作者隔离；check_eval_leakage.py 对 dev 与 test 各自双向通过；
     test gold 由 Owner 终标并在预注册文件签字"校准期（P3/P4）不查看 test 内容"。
工具：扩容/切分脚本 + split 注册（dataset.py 增 ops dev/test split 标识）。
```

### 1.3 预注册成功标准（带时间戳，校准开始前提交）

`docs/Q4_P2_PREREGISTER.md`：写定 §3.6 Gate（test 集上 precision@authorized≥0.60 ×
over_escalation≤0.30 × unauthorized_blocked=1.00 × F11=F13=0 ⇒ triad=True），阈值数值、
dev/test 条数、run_id 计划（`q4-p5-selection-calibrated`）。**先提交此文件，再开始 P3 改逻辑**——
commit 时间戳即"未事后改标准"的证据。

------

## 2. Q4-P3：检测修复 + 路由校准（Codex；validator 不动）

### 2.1 检测修复（§3.3，承重）— `app/govern/conditions.py`（+ ingest/overlay）

**根因 A — 修 superseded_by 丢失：**
```text
让 deprecated 文档的 superseded_by 经 ingest/overlay 落到 chunk 元数据并被 GovernanceSignals 读到。
排查链：metadata_overlay.yaml → apply_metadata_overlay → chunk 落字段 → GovernanceSignals 抽取。
单测：含 deprecated+superseded_by 的合成 chunk → GovernanceSignals.superseded_by 非空。
```

**根因 B — stale 检测增"overlay_relation_note"分支：**
```text
STALE_PROCEDURE 触发条件改为【二选一即触发】：
  (a) top-k 含 status==deprecated 且 superseded_by 非空的 chunk；或
  (b) top-k 含 active chunk，其 overlay_relation_note.type=="stale_procedure"
      （指向一个 deprecated/superseded 目标）—— 不要求 deprecated 文档本身被检索到。
单测：纯 SOP 交叉引用（无 deprecated chunk）→ 必出 STALE_PROCEDURE（覆盖 ora-002/003 型）。
```

### 2.2 路由校准（§3.4，次要）— `app/govern/conditions.py` + `controller.py`

**伪 PERMISSION_BLOCKED 修复（压过度升级，4 例的根）：**
```text
PERMISSION_BLOCKED 只在【真授权失败】时记：authorized_actor==False（角色对请求动作无权），
  或 ACL 拦截移除了【答案实际所需】证据导致 evidence 不足。
授权 actor + 干净证据 sufficient + 仅【无关】restricted 邻居被拦 → 不记 PERMISSION_BLOCKED，
  不得短路 escalate（让真实 condition：stale/config/xref 正常路由到对应动作）。
单测：authorized=True + 无关 restricted 邻居 + evidence sufficient → conditions 不含 PERMISSION_BLOCKED。
```

**ora-012 漏升级（镜像，1 例）：**
```text
诊断 ora-012 evidence_decision 为何 sufficient（gold 期望 insufficient）：
  若 evidence gate 阈值/计数对该 case 误判 → 在不破坏其它 case 的前提下校准；
  若该 case 设计本身边界模糊 → 记入 P2 扩容时重审，必要时替换为更干净的 insufficient case。
目标：真·证据不足 → INSUFFICIENT_EVIDENCE → escalate（escalation_when_insufficient > 0）。
```

**控制器优先级**：保持 escalate 仅由 PERMISSION_BLOCKED(真) / INSUFFICIENT_EVIDENCE / 无合法动作 触发；
伪 permission 修掉后，stale/config/xref 自然落到 flag_stale / open_remediation_ticket。

### 2.3 单测矩阵（Codex）

```text
# 检测
test_superseded_by_survives_ingest        deprecated+superseded chunk → signals.superseded_by 非空
test_stale_from_deprecated_chunk          根因A型 → STALE_PROCEDURE
test_stale_from_overlay_relation_note     根因B型（纯SOP交叉引用，无deprecated）→ STALE_PROCEDURE
test_stale_routes_to_flag_stale           STALE_PROCEDURE + 授权 + sufficient → 控制器选 flag_stale
# 路由
test_authorized_irrelevant_restricted_no_permission_blocked  伪越权不再记 PERMISSION_BLOCKED
test_real_unauthorized_still_blocked      ora-009/010/011 型仍 escalate（安全地板不破）
test_insufficient_evidence_escalates      真·不足 → escalate
# 不变式
test_validator_unchanged                  validator 行为与 Q3 完全一致（回归锁）
```

------

## 3. 验收（P2 + P3）

```text
[ ] ops 集扩到 ~36，dev/test 物理分文件，leakage 各自双向通过，dataset.py 注册 split
[ ] Q4_P2_PREREGISTER.md 先于 P3 逻辑改动提交（时间戳为证）
[ ] 检测：根因 A/B 修复，§2.3 检测单测全过；flag_stale 在合成 stale case 上可被提议
[ ] 路由：伪 PERMISSION_BLOCKED 消除、真越权仍拦、ora-012 类可升级
[ ] validator.py 零改动；anti-gaming 阈值常量未动；mock 不入 headline 合约不变
[ ] ruff 干净；pytest 全绿；Q1–Q3 回归不变（含 test_validator_unchanged）
```

> P3 完成后进 P4：**仅用 dev 集**迭代至 triad=True 并冻结配置写入 manifest；再 P5 跑【留出 test】
> k=3 真实 run `q4-p5-selection-calibrated` —— test 上翻 triad 即 Q4 正结果达成（§3.6 Gate）。
> 提醒：当前活动索引已是 ops（P1 诊断重建所致），Q4 全程用 ops；做 Q1/Q2 复现时再 rebuild 回 public。
