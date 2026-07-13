# Q5-P5 Dev V3 Authoring Report

版本：v1
日期：2026-07-13
状态：**DATA AND PREREG FROZEN; IMPLEMENTATION PENDING**

## 1. 数据结构

活动 `data/q5/dev/` 已升级为 q5_dev v3，规模仍为 36：deterministic/semantic/adversarial 各 12。
semantic 三族各四案，每案同时进入一组 within-policy pair 和一组 cross-policy pair，共两套各六组。

| Family | Within-policy groups | Cross-policy state groups |
| --- | --- | --- |
| Policy exception | waiver / tracking | scope match / mismatch |
| Change lifecycle | cutover / archival hold | completed / planned |
| Incident impact | outage page / failover | outage / degraded |

固定状态表在 v2 的 solvability 为 1.00，在 v3 为 0.50。当前 deterministic mock 的 semantic success
也为 0.50，证明 authoring 没有向测试模型提供隐藏捷径。

## 2. 机器锚点

| Artifact | SHA-256 |
| --- | --- |
| tasks | `bafd1e7a416526229a919b223f4ccdc771175c72c0d928b5e28c9485840da0be` |
| runtime cases | `3a528896e096662f9fe5bd68280807db229827392e74cecb05ecffba2d021c49` |
| environment | `dd9371eb0f09e15db3b2c46c743ecabfd19cc4c9339c15eabd7076f11192fe89` |
| Gold | `3dd75f63a9d97761f9c47a24f6ae0710e67a4f86b45b5efc6bc181c7eddd777b` |
| corpus | `fbb70816da16ecbf123b2f7ebbb25978692462e8a9a5e7714d5ea3c8678b64d7` |
| manifest | `75934cc45a33d13f5eca720c9000babe0f63f1f00bddb0f43155d5bb37251b78` |

`q5-pre-run-v3` 的 11 项检查全部通过，包括双轴 pair closure、动态状态不披露、ACL/gate replay、
tool grounding、manifest 与 receipt。v2 原数据按原哈希归档于 `data/q5/archive/dev-v2/`。

## 3. Zero-request Diagnostics

`q5-dev-v3-mock-plan-authoring-k3` 完成 324 trials 并通过 protocol-v3 验签：

- Rule/LLM-only/Hybrid semantic trajectory-qualified success 均为 0.50；
- duplicate successful observation 为 0；
- post-observation terminal rate 为 1.00；
- G0/G2/G3/G5 通过；G1 失败符合 fixed-table mock 预期；G4 未执行；
- external/LLM requests 为 0。

本 mock 只证明数据与 Agent loop 可执行，不构成 LLM 价值证据。
