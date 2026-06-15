# Phase 2 Judge Implementation Spec (custom judge + agreement harness)

交给：Codex。出规格：Claude（已核 `manual_audit_v1_labels.jsonl` 数据形状）。
协议依据：`docs/JUDGE_PROTOCOL.md`（候选、偏置红线、选型门、prompt 草案 §6）。
对应：ROADMAP Phase 2 P2-01..P2-06。

------

## 0. 这个 harness 验证什么 / 不验证什么（先读）

锚点集是今天的 15 条人工标签（`manual_audit_v1_labels.jsonl`，annotator=owner）：
**11 supported / 4 weak / 0 unsupported / 0 wrong_side**。

直接后果，必须写进所有产出：

- 锚点里 **没有一条 unsupported、没有一条 wrong_side**。因此这个 harness
  **无法验证** judge 检测"无支持引用"和"错误一侧引用"的能力——而这两者恰是最
  要紧的失效模式。judge 在这 15 条上拿满分也说明不了它能抓真正的坏引用。
- 真正能测的只有一件事：judge 能否把 11 条 clear-supported 和 4 条
  degenerate-weak 区分开（binary 轴）。这是有意义但很窄的信号。
- 因此本 spec **强制加一个 discriminative probe set**（§5）：人工构造的
  必然 unsupported / wrong_side 样本，测 judge 的判别力下限。judge 在真锚点上
  达标但在 probe 上抓不住植入的坏引用 → 判为不可用。
- wrong_side 的真实锚点要等 hard-negative 重写 real run（C2-05 / Q2-W1）才有；
  在那之前，judge 对 wrong_side 的验证是 probe-only，报告须声明此局限。

------

## 1. 输入与产物

输入（只读）：
- `data/citation_audit/manual_audit_v1_labels.jsonl` — 人工锚点（ground truth）。
  每行：`audit_id, case_id, eval_split, claim_text, citation_chunk_ids,
  cited_text_snapshot{chunk_id:text}, label, wrong_side_citation`。
- `data/citation_audit/judge_pass_v1_gpt_labels.jsonl` — 既有 GPT pass，
  作为额外参考列（非正式候选）。

产物：
```text
data/eval_runs/judge-agreement-v1/
  ragas_verdicts.jsonl
  deepeval_verdicts.jsonl
  custom_verdicts.jsonl
  probe_verdicts.jsonl
  agreement_summary.json
docs/JUDGE_AGREEMENT_REPORT.md   # 数据由 Codex 产出，散文结论 Claude 后补
```

## 2. Judge 模型配置（硬约束）

已在 `.env` / `.env.example` 写好（key 待 Owner 填），Codex 需新增对应 settings
字段并实现 client：

```text
JUDGE_LLM_PROVIDER=xiaomi          # 视作 OpenAI-compatible，base_url 驱动
JUDGE_LLM_MODEL_NAME=mimo-v2.5-pro
JUDGE_LLM_BASE_URL=https://api.xiaomimimo.com/v1   # 小米官方 API
JUDGE_API_KEY=<owner fills>
```

- `xiaomi` 走 OpenAI-compatible client（复用 openai 路径 + base_url 即可）。
- base_url/model 假定 **小米官方平台**（model id 无 vendor 前缀）。若 key 来自
  OpenRouter/WaveSpeed/Puter，base_url 与 model id 不同（如 `xiaomi/mimo-v2.5-pro`），
  须相应改 `.env`。
- **必须与系统主模型不同家族**（系统是 DeepSeek；MiMe/Xiaomi 满足）。启动时加 guard：
  若 judge 家族 == 系统家族 → 直接报错退出，不许跑（self-preference bias 红线，
  JUDGE_PROTOCOL §3）。guard 建议比对 **模型家族**而非仅 provider 字符串。
- 三个候选共用同一 judge 模型，隔离的是方法/prompt 不是模型。
- `temperature=0`，结构化输出，模型版本 pin 进 `agreement_summary.json`。
- judge 只能看到 `claim_text` + `cited_text_snapshot` 的文本值。
  **禁止**传入 human label、gold answer、system_name、case 的 expected_behavior。
  加一个单测断言这些字段不出现在 judge 的 prompt 里。

## 3. 候选实现

新包 `app/eval/judge/`：

```text
base.py          JudgeVerdict{label: supported|weak|unsupported,
                              wrong_side: bool, rationale: str}
                 BaseJudge.judge(claim_text, cited_texts: list[str]) -> JudgeVerdict
custom_judge.py  J-C，prompt 用 JUDGE_PROTOCOL §6 草案；JSON 输出 + 解析 fallback
                 （解析失败记 warning，label 记 'unsupported' 保守处理，不静默丢）
ragas_judge.py   J-A：RAGAS faithfulness 适配
deepeval_judge.py J-B：DeepEval G-Eval / FaithfulnessMetric 适配
```

**输入对齐（决定对比是否公平，JUDGE_PROTOCOL §2）**：三个候选评的是**完全相同**
的 (claim_text, cited_texts) 对。对 RAGAS：把 `claim_text` 当 answer、
`cited_texts` 当 contexts 提交，**绕过 RAGAS 自带的答案分解**——否则它产出的
statement 单元和人工锚点单元对不齐，agreement 无法计算。框架候选按出厂默认配置
跑（记录版本），不调优。

候选输出统一映射到 `JudgeVerdict.label`：框架若只给二分（faithful/not）→
映射为 supported / unsupported（weak 仅 J-C 原生支持，框架候选的 weak 记为
unsupported 侧并在报告注明粒度差异）。

## 4. Agreement Harness — `app/eval/judge/agreement.py` + `scripts/run_judge_agreement.py`

对每个候选 vs 人工锚点，计算（定义照 JUDGE_PROTOCOL §4）：

```text
bin(x) = 'supported' if x=='supported' else 'not_supported'
binary_agreement = mean(bin(judge)==bin(human))            # 主轴，三候选可比
exact_agreement  = mean(judge.label==human.label)          # 3-way，仅 J-C 有意义
cohen_kappa      = binary 上的 kappa                        # 防 11/4 偏态虚高
per_stratum      = external(13) / obfuscated(2) 分别计数（obfuscated n<5 只报计数）
bootstrap_ci     = 对 15 条有放回重采样 1000 次，报 binary_agreement 的 95% CI
```

额外参考（不参与选型，仅报告）：candidate-vs-candidate、candidate-vs-GPT
（用 `judge_pass_v1_gpt_labels.jsonl`）。

`agreement_summary.json` 须含：每候选上述指标、judge 模型名+版本、anchor n、
probe 结果（§5）、`headline`/`judge_based` 提示字段、生成时间。

## 5. Discriminative Probe Set（判别力下限，强制）

新文件 `data/citation_audit/discriminative_probes.jsonl`，**5 条人工构造的合成样本**
（Claude 起草，明确标 `synthetic=true`，绝不混入真锚点 / agreement-on-reals）：

```text
3 条 unsupported：取一个真 claim，配一段主题明显不相关的真 chunk 文本
   （如 CORS 的 claim 配 file-upload 的 chunk）。期望 judge.label=unsupported。
2 条 wrong_side：取一个 claim，配一段讲"高度相似但不同"主题的 chunk
   （如 path parameters 的 claim 配 query parameters 的 chunk）。
   期望 judge.wrong_side=true（label 可 weak/unsupported）。
```

Probe 是**下限测试**，与真锚点的 agreement 分开报告。判据：
`probe_floor = 正确判定的 probe 数 / 5`。

## 6. 选型门（JUDGE_PROTOCOL §5，G2 为硬门）

候选**可用于下游指标**当且仅当：

```text
G2（硬）：binary_agreement ≥ 0.80（15 条真锚点上）
PROBE（硬，本 spec 新增）：probe_floor ≥ 4/5
G1（参考，不阻塞）：不单独估人工自一致率，G1 略过
```

结果：
- ≥1 候选过 G2+PROBE → 选 binary_agreement 最高者；并列时优先 J-C（原生 3-way +
  wrong_side，正是未来最需要自动覆盖的 F4 方向）。
- 无候选同时过 G2+PROBE → **不部署 judge**，claim-support 维持 human-only，
  Phase 2 中依赖 judge 的项（运行时 verifier、judge-based 全量 unsupported_claim_rate）
  降级，并如实报告。**不许为了上线 judge 而放宽门。**

## 7. 验收标准

```text
1. 二次家族 guard：judge 家族==系统家族时报错退出（单测）。
2. 信息隔离：judge prompt 不含 human label / gold / system_name（单测）。
3. 三候选在 15 真锚点上各产 verdicts.jsonl；agreement_summary.json 含全部 §4 指标 + CI。
4. probe set 5 条跑完，probe_floor 落 summary。
5. custom judge 解析失败有 fallback（保守 unsupported + warning），不崩、不静默。
6. 所有 judge-based 字段带 judge_based 标记；summary 不得标 headline_eligible。
7. ruff + 新增单测全绿；不破坏既有 150 unit。
8. 不消耗 DeepSeek token（judge 走二次家族）；总调用 ~120 次，成本 <¥30。
```

## 8. 不做 / 诚实红线

```text
- 不把 judge 输出当 "citation accuracy X%"；judge_based ≠ 人工审计。
- 不外推 easy-split 的高 agreement 到硬判断；报告须写 n=15 + 无 unsupported/wrong_side
  真锚点 + probe-only 验证 wrong_side 的三重局限。
- 不调优框架候选（破坏 off-the-shelf vs domain-tailored 对比）。
- judge 选型只用 G2+PROBE；自一致率 G1 不可得，不得临时编一个充数。
- wrong_side 的真实验证待 C2-05 hard-negative 重写锚点；在那之前结论标 "partial"。
```

## 9. 后续（本 spec 完成后）

- Claude：数据落盘后写 `JUDGE_AGREEMENT_REPORT.md` 散文结论（诚实口径）。
- 若选出 judge：进 P2-05（judge-based unsupported_claim_rate 全量回填，带 judge_based）
  + P2-06（CI 回归门禁）。
- 运行时 verifier（Phase 3 决议 B）继承本结论；阈值（哪些 label 放行）在
  agent 设计冻结会定，默认只 supported 放行。
```
