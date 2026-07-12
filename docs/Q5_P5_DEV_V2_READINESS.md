# Q5-P5 Dev V2 Readiness Report

版本：v1
日期：2026-07-12
状态：**REAL RUN BLOCKED BY G3 SYNTHETIC DIAGNOSTIC**

------

## 1. C1R 独立审核

Commit `71b25e51553ffa0d389be046ece0f33961045829` 审核通过：

- 新运行统一产出四类 protocol-v2 artifacts；
- verifier 冻结分派 v1，并严格交叉重算 v2；
- 旧 DeepSeek real run 使用 v1 Gold 重新验签通过，17 个 artifact 哈希不变；
- 新 v2 mock 的 raw、graded、metrics、gates 均完成独立验签；
- G4 使用 `trajectory_qualified_success`，observation attempted/completed 与四类 cost basis 均可区分。

未发现阻断 C2 数据 authoring 的实现缺陷。

------

## 2. q5_dev V2 Authoring

活动 `data/q5/dev/` 已升级为 36-case v2：

- deterministic / semantic / adversarial 各 12；
- semantic query 不披露动态 environment state；
- 12 个 semantic case 构成 6 组 action-divergent counterfactual pairs；
- counterfactual/family/state tags 仅存在于 grader Gold；
- pre-run schema 为 `q5-pre-run-v2`，10 项静态检查全部通过；
- 第一次 real-dev 使用的 v1 数据完整归档于 `data/q5/archive/dev-v1/`。

活动 v2 锚点：

| Artifact | SHA-256 |
| --- | --- |
| tasks | `eecc6bd418051638c687b4b86413dca94c4339ad36421c7576e4a4ec75ddb68f` |
| runtime cases | `07bc4992b6e6ccd13d71d8d3a90de0d81b33a6028146e46f53288f1df437aaeb` |
| environment | `22a2a356ce35466a0cc7a8ff7f19d47919194ca7c8a6470af3488f805d4fb06a` |
| Gold | `e7c0e96e0eb50f752c2132a4c7ece7577b605d3c585c721a1a255aaf70772a32` |
| corpus | `923ef2c488db1d40971d9333e1cd98e51e179a5b9a1f3c46c543f7d0bc98acb4` |
| manifest | `1b36de2b59b79c09b71e8435a72f45bb91bd11e55a535851f772b21f13cf1874` |

------

## 3. Synthetic K=3 Diagnostic

Run：`q5-dev-v2-mock-c2-precommit-primary-k3`，324/324 trials，protocol-v2 验签通过。

| System | Overall | Semantic | Trajectory-qualified | Required obs recall | Calls | Tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rule | 0.8333 | 0.5000 | 0.8333 | 1.0000 | 0 | 0 |
| LLM-only | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 132 | 31,626 |
| Hybrid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 78 | 20,631 |

- trajectory-qualified semantic uplift：`0.5000`，bootstrap 95% CI `[0.25, 0.75]`；
- call avoidance：`40.91%`，G3 call ratio `0.59091`，通过；
- token avoidance：`34.77%`，G3 token ratio `0.65233`，**失败**；
- G0 / G1 / G2 / G5 通过；G4 未运行；
- required observation、tool schema、invalid transition 与 safety 路径均通过。

因此数据和 Agent 机制已表现出预期方向，但在 token Gate 通过前不得授权 real run。

------

## 4. G3 诊断与 Batch 5-C3

token 分解：

| Surface | Hybrid tokens | LLM-only tokens |
| --- | ---: | ---: |
| Semantic | 19,182 | 19,182 |
| Deterministic | 0 | 6,720 |
| Adversarial | 1,449 | 5,724 |

Hybrid 没有多跑 semantic call；近线失败来自 semantic observe prompt 携带完整 Pydantic JSON Schema，
其中 title/default 等展示元数据不参与 validator 语义，却在两步 observation loop 中重复传输。

Batch 5-C3 只允许：

1. 从现有 Pydantic args model 单源派生 canonical compact schema；
2. 保留字段名、类型、enum、required、`additionalProperties=false` 与 grounded reference values；
3. 删除不影响校验的 title/default/展示元数据，并保证 prompt/verifier 使用同一 canonical form；
4. 增加 parity、fail-closed、prompt contract 与 token regression 测试；
5. 不修改 q5_dev、Gold、Gate、路由、模型策略或 baseline；
6. external/LLM requests 保持 0，完成后重跑同配置 synthetic k=3。

通过标准：四项质量/安全结果不退化，G3 call ratio `<=0.60`，token ratio `<=0.65`。若仍失败，
返回 plan/report 诊断，不得直接运行 DeepSeek。
