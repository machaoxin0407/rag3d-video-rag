# AI 辅助标注与单人复核协议（2026-07-22）

## 1. 适用范围

本协议适用于新增公开视频候选、视频场景标签和首批 100 个视频检索问题。此前 11 条视频的 A/B/C 审核记录作为历史证据保留，不追溯改写；从本协议生效日起，新增数据采用“AI 预标注 + R1 单人最终复核”。

AI 不是最终标注员。论文金标准只采用 R1 已完成复核的结果，并如实披露人工复核人数。

## 2. 角色和责任

- AI：生成技术筛选、内容标签、候选时间边界、许可证据摘要、风险提示和排除建议；
- R1：查看来源页和完整视频，修正 AI 标签，核查许可、隐私与安全风险，并作最终接受/拒绝决定；
- 项目负责人：冻结规则、抽样种子、数据切分和模型版本，批准重大范围变更。

## 3. 视频候选复核

### 3.1 AI 阶段

每条候选至少保留以下原始字段：

```text
record_id, model_id, model_revision, prompt_version,
expected_product_class, predicted_product_class,
procedure_relevance, functional_step_visible,
visual_evidence, uncertainty, machine_decision,
technical_decision, sampled_frame_paths
```

AI 的输出不得覆盖。人工修正写入独立的 `corrected_*` 字段。

### 3.2 R1 工作量

R1 必须完成：

1. 全量复核所有 AI 保留项；
2. 对 AI 拒绝项执行 20% 抽查，样本数使用 `ceil(N × 0.20)`；
3. 抽样采用固定种子 `candidate-reject-audit-v1`，按产品类别分层，并保证每类至少一条；
4. 抽查发现 AI 误拒时，将该项转入完整复核，补齐许可证据和最终标签；
5. 所有最终接受项均打开来源页并查看完整视频，不能只看标题或采样帧。

当前自动生成的队列为 `data_video/manifests/candidate_review_queue.csv`：26 条 AI 保留项全量复核，9 条 AI 拒绝项抽查，共 35 条。

### 3.3 R1 必填字段

```text
reviewer_id=R1
review_status=pending|in_progress|completed
license_evidence_status=pending|verified|failed|unclear
corrected_product_class
corrected_procedure_relevance=yes|no|uncertain
corrected_functional_step_visible=yes|no|uncertain
privacy_risk=none|low|high|uncertain
safety_risk=none|low|high|uncertain
correction_reason
final_decision=accept|reject|hold
dataset_split=development|source_disjoint_test|excluded
reviewed_at=<ISO-8601 timestamp>
```

最终接受的必要条件：`review_status=completed`、`license_evidence_status=verified`、`final_decision=accept`，且 `dataset_split` 不是 `pending` 或 `excluded`。

## 4. 100 个检索问题的复核

AI 为每个问题—场景候选生成 0–3 级相关性、最相关时间边界、证据文本和不确定性。R1 对全部 100 个问题进行全量复核，而不是抽样复核。

每个问题至少保存：

```text
query_id, query_text, product_class, query_type, split,
candidate_scene_id, ai_relevance_grade, ai_start_time, ai_end_time,
ai_evidence, ai_uncertainty,
r1_relevance_grade, r1_start_time, r1_end_time,
r1_source_leakage, correction_reason, review_status, reviewed_at
```

相关性等级固定为：

- 0：不相关；
- 1：仅同产品或背景相关，不能直接回答；
- 2：部分回答或展示相邻步骤；
- 3：直接回答，并有有效视觉/语音/OCR 证据。

R1 在复核前不得看到被比较检索方法的排名或分数。问题和来源切分冻结后，测试集不得用于提示词、阈值、融合权重或候选数调优。

## 5. AI 标注提示词要求

正式运行时提示词必须要求模型：

1. 只根据可见画面、ASR、OCR 和来源元数据判断，不补全不可见步骤；
2. 区分目标产品、外观相似设备和仅标题命中；
3. 对功能步骤、隐私和危险动作分别判断；
4. 证据不足时输出 `uncertain`，不得强猜；
5. 输出严格 JSON，并引用支持判断的帧或时间段；
6. 不把模型预测写成最终人工结论。

推荐系统提示词：

```text
你是产品操作视频的数据预标注模型。只使用输入中可见的帧、ASR、OCR和来源元数据；不得推断未出现的动作、型号或授权事实。判断视频是否属于目标产品，是否包含可用于操作、维护或故障检索的功能步骤，并标记隐私、安全与许可不确定性。证据不足时输出 uncertain。输出必须符合给定 JSON Schema，并为每个结论给出时间戳或帧证据。你的输出是 AI 预标注，不是最终金标准。
```

模型 ID、精确 revision、推理框架、采样帧策略、提示词全文、JSON Schema、随机种子和运行日期必须写入 run manifest。若模型不能保证完全确定性，应缓存原始输出，并通过固定输入复现，而不是声称 bitwise deterministic。

## 6. 质量统计

论文和数据卡至少报告：

- AI 保留项数量及 R1 最终接受率；
- AI 保留项标签修正率，按产品类别和字段分层；
- AI 拒绝项总体数量、抽查数量及抽查误拒数；
- 抽查误拒率及 Wilson 95% 置信区间；
- 技术、内容、许可、隐私和安全各原因的排除数量；
- R1 实际复核时间和未完成项数量。

若 9 条拒绝抽查中发现误拒，应报告 `k/9` 和区间估计，不得把它直接描述成整个数据集的精确误拒率。必要时扩大抽查比例；高风险类别可全量复查。

只有一名人工复核人，因此不计算 Cohen's Kappa、Fleiss' Kappa 或 Krippendorff's Alpha。可报告的是 AI—R1 一致率、人工修正率和抽查误差，但它们不能被称为“标注员间一致性”。

## 7. 论文方法表述

英文建议表述：

> Candidate videos were pre-annotated by a vision-language model. A single reviewer verified every AI-retained candidate and all query-relevance labels, and audited a deterministic, product-stratified 20% sample of AI-rejected candidates. The reviewer could correct product, procedural, temporal, privacy, and safety labels. We report correction rates and reject-audit error estimates with confidence intervals; no inter-annotator agreement is claimed.

中文建议表述：

> 候选视频首先由视觉语言模型生成预标注。一名人工复核人对全部 AI 保留候选和全部检索问题相关性标签进行核验，并对 AI 拒绝候选进行固定种子、按产品类别分层的 20% 抽查。复核人可修正产品、过程、时间、隐私和安全标签。本文报告修正率及拒绝抽查误差的置信区间，不声称标注员间一致性。

## 8. 局限性

- 单人复核不能测量不同标注员之间的主观分歧；
- 20% 拒绝抽查的样本量较小，误拒率区间可能较宽；
- AI 和 R1 可能共享对显著视觉线索的偏差；
- 许可证据核查是项目内部合规流程，不构成法律意见；
- 若期刊或审稿人要求独立双人测试集标注，应补充第二复核人，而不是改写当前方法。
