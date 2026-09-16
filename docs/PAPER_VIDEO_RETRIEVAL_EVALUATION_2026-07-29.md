# 论文正式视频检索评测（2026-07-29）

## 1. 冻结状态

论文正式 v1 相关性集已经冻结：

- 100 个问题；
- 725 个唯一视频场景；
- 3,775 个问题–场景判断；
- 每行至少由两名独立人类复核员实际看片；
- 146 个争议行由第三名人类裁决；
- 第三轮全量交叉复核一致率 95.1%；
- 3,775/3,775 行完成机械 QC。

最终等级分布为：

| 等级 | 行数 |
|---|---:|
| 0 | 2,092 |
| 1 | 1,289 |
| 2 | 267 |
| 3 | 127 |

100 个问题均在候选池内具有至少一个等级 ≥1 的场景；75 个问题具有至少一个等级 ≥2 的场景。正式二值相关性定义为 `grade >= 2`。

冻结产物：

```text
data_video/manifests/paper_qrels_v1/paper_video_qrels_graded_v1.csv
data_video/manifests/paper_qrels_v1/paper_video_qrels_graded_v1.txt
data_video/manifests/paper_qrels_v1/paper_video_qrels_binary_ge2_v1.txt
data_video/manifests/paper_qrels_v1/paper_video_qrels_manifest_v1.json
```

最终人工复核工作簿 SHA-256：

```text
fdfbc924deeef5753cd536a5b2305edffe72601bbe7512609e24dcb4591802dd
```

正式 graded qrels SHA-256：

```text
463eeef7fabacb09f7b974cc34400e5e92b07afff2a412c76c837dc6d588d412
```

## 2. 评测设置

评测对象为冻结候选池中的五种原生检索模式：

1. BM25；
2. Dense；
3. Visual；
4. Hybrid（BM25 + Dense）；
5. Tri-Hybrid（BM25 + Dense + Visual）。

每种模式均使用冻结的 Top-20 排名；每种模式共 1,967 条结果，每题 19–20 条，平均 19.67 条。五种模式均为真实原生模式，无静默回退。

指标口径：

- nDCG 使用分级增益 `2^grade - 1`，100 个问题全部纳入；
- MAP、MRR、Recall 和 Precision 使用 `grade >= 2` 的二值相关性；
- 二值宏平均主结果使用 75 个具有正例的问题；
- 同时保存将 25 个无等级≥2正例问题计为 0 的保守 coverage-adjusted 指标；
- Recall 和 MAP 是对冻结 Top-20 联合池的 pool-relative 结果，不声称是全语料穷尽判断。

## 3. 主结果

| Mode | K | N_bin | nDCG | MAP | MRR | Recall | Precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 10 | 75 | 0.469 | 0.299 | 0.547 | 0.484 | 0.188 |
| BM25 | 20 | 75 | 0.506 | 0.324 | 0.555 | 0.632 | 0.124 |
| Dense | 10 | 75 | 0.593 | 0.417 | 0.629 | 0.634 | 0.280 |
| Dense | 20 | 75 | 0.616 | 0.444 | 0.633 | 0.745 | 0.170 |
| Visual | 10 | 75 | 0.588 | 0.400 | 0.594 | 0.652 | 0.261 |
| Visual | 20 | 75 | 0.608 | 0.421 | 0.597 | 0.723 | 0.157 |
| Hybrid | 10 | 75 | 0.575 | 0.435 | 0.663 | 0.614 | 0.269 |
| Hybrid | 20 | 75 | 0.599 | 0.462 | 0.667 | 0.731 | 0.163 |
| **Tri-Hybrid** | **10** | **75** | **0.647** | **0.509** | **0.722** | **0.716** | **0.299** |
| **Tri-Hybrid** | **20** | **75** | **0.655** | **0.539** | **0.724** | **0.813** | **0.179** |

在 K=10 时，Tri-Hybrid 相对各指标的最强单一/双路基线取得：

- nDCG：绝对提升 0.054，相对提升 9.2%；
- MAP：绝对提升 0.074，相对提升 17.0%；
- MRR：绝对提升 0.059，相对提升 8.9%；
- Recall：绝对提升 0.065，相对提升 9.9%。

## 4. 配对统计检验

对 100 个问题的 nDCG@10 执行 10,000 次配对 bootstrap，固定种子 `20260729`：

| Tri-Hybrid 对比 | nDCG@10 差值 | 95% CI | 双侧 p |
|---|---:|---:|---:|
| BM25 | 0.178 | [0.146, 0.210] | 0.0002 |
| Dense | 0.054 | [0.016, 0.093] | 0.0068 |
| Visual | 0.059 | [0.022, 0.096] | 0.0016 |
| Hybrid | 0.072 | [0.045, 0.099] | 0.0002 |

所有置信区间均未跨越 0。

## 5. 分产品 nDCG@10

| Product | Queries | BM25 | Dense | Visual | Hybrid | Tri-Hybrid |
|---|---:|---:|---:|---:|---:|---:|
| Air Fryer | 17 | 0.403 | 0.573 | 0.563 | 0.527 | **0.625** |
| Espresso Machine | 17 | 0.569 | 0.684 | 0.671 | 0.689 | **0.772** |
| Pressure Cooker | 17 | 0.439 | 0.553 | 0.602 | 0.557 | **0.623** |
| Printer | 17 | 0.453 | 0.566 | 0.548 | 0.581 | **0.642** |
| Vacuum | 16 | 0.337 | 0.487 | **0.563** | 0.473 | 0.543 |
| Washing Machine | 16 | 0.617 | **0.693** | 0.580 | 0.622 | 0.672 |

Tri-Hybrid 在 6 个产品类别中的 4 个类别取得最佳 nDCG@10。Vacuum 由 Visual 最佳，Washing Machine 由 Dense 最佳，说明不同产品的视觉线索和文本线索贡献存在差异。

## 6. 论文方法表述建议

可在论文中写为：

> We constructed a pooled relevance benchmark from the native top-20 outputs of five retrieval configurations. Each of the 3,775 query–scene pairs was independently inspected by at least two human reviewers, and disputed cases were adjudicated by a third human reviewer. Relevance was graded on a four-level scale (0–3). We report graded nDCG using a gain of \(2^{grade}-1\), and binary MAP, MRR, and recall using grades 2–3 as relevant. Binary macro metrics are computed over the 75 queries containing at least one grade-2-or-higher judgment; coverage-adjusted results over all 100 queries are reported separately.

结果表述建议：

> Tri-Hybrid achieved the strongest overall performance, reaching an nDCG@10 of 0.647, MAP@10 of 0.509, MRR@10 of 0.722, and Recall@10 of 0.716. Its nDCG@10 improvement over the strongest non-tri-modal baseline was 0.054 absolute (9.2% relative), and paired bootstrap testing confirmed a significant improvement over dense retrieval (95% CI [0.016, 0.093], p=0.0068).

## 7. 结果文件

```text
reports/paper_retrieval_eval_v1/paper_retrieval_evaluation_v1.json
reports/paper_retrieval_eval_v1/paper_retrieval_metrics_summary_v1.csv
reports/paper_retrieval_eval_v1/paper_retrieval_metrics_per_query_v1.csv
reports/paper_retrieval_eval_v1/paper_retrieval_metrics_breakdown_v1.csv
reports/paper_retrieval_eval_v1/paper_retrieval_table_v1.md
```

## 8. 结论与限制

正式 qrels、五模式排名、指标和统计检验已经冻结并可复现。Tri-Hybrid 是当前总体最优模式。

必须同时披露以下限制：

1. 候选判断来自五种模式 Top-20 的联合池，池外场景未被穷尽判断；
2. 25 个问题在联合池内没有等级≥2的场景，因此二值主指标只对 75 个可评测问题宏平均；
3. 结果基于当前 78 条论文视频和来源隔离切分，不应外推为开放世界性能；
4. 产品分组只有 16–17 个问题，分产品结果用于诊断，不宜做过强显著性结论。
