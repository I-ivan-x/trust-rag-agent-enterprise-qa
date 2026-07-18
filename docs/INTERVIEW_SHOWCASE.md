# Interview Showcase Corpus

`data/showcase/interview-v1/` 是一个公开安全、完全虚构的 SaaS 发布事故语料包。它只用于在面试页面中演示以下治理路径：

1. 接收“诊断并回滚”的事故请求；
2. 采用当前运行手册，隔离过期和无权限资料；
3. 读取发布状态与错误率；
4. 提出回滚到上一健康版本；
5. 重新检查动作权限；
6. 在权限不足时等待事故负责人审批，不产生副作用。

## 证据边界

Manifest 固定声明：

- `data_mode=synthetic`
- `use=demonstration_only`
- `headline_eligible=false`
- `formal_evaluation=false`
- `model_requests=0`
- `external_requests=0`

该语料不能成为公开 Claim、正式评测 `source_artifacts` 或主结论的来源。`scripts/verify_showcase_isolation.py` 会校验精确文件集合、逐文件 SHA-256、轨迹一致性和正式 Claim 隔离；`scripts/build_interview_showcase.py --check` 还会校验前端演示视图没有漂移。

## 本地校验

```powershell
py -m uv run --frozen python scripts/verify_showcase_isolation.py
py -m uv run --frozen python scripts/build_interview_showcase.py --check
```

语料不对应任何真实公司、客户、凭据、运行环境或生产事故。
