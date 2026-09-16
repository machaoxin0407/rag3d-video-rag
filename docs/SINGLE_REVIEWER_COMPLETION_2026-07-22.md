# R1 单人视频复核完成记录（2026-07-22）

## 1. 完成状态

- 输入工作簿：`R1_video_review_workbook.xlsx`；
- 完整记录：35/35；
- `review_status=completed`：35/35；
- 最终接受：19；
- 最终拒绝：16；
- 暂缓：0；
- 所有接受项许可证据：`verified`；
- 所有接受项均具有人工确认的目标产品类别、过程相关性和可见功能步骤；
- 所有拒绝项均记录排除原因并使用 `dataset_split=excluded`。

工作簿未直接覆盖原始 AI 字段。人工结果通过 `import_single_reviewer_review.py` 与冻结队列逐字段核对后，才合并到 `candidate_review_queue.csv`。

## 2. AI 保留项复核结果

26 条 AI 保留项中：

| 指标 | 结果 |
|---|---:|
| R1 最终接受 | 19 / 26（73.1%） |
| R1 最终拒绝 | 7 / 26（26.9%） |
| 产品类别修正 | 1 / 26（3.8%） |
| 过程相关性修正 | 5 / 26（19.2%） |
| 可见功能步骤修正 | 3 / 26（11.5%） |

过程相关性比较时，将 AI 的 `operation/setup/maintenance/troubleshooting` 映射为 `yes`，将 `promotion/component_overview/irrelevant` 映射为 `no`，`uncertain` 保持不变。

## 3. AI 拒绝项抽查

- AI 拒绝池：42；
- 固定种子、按存在拒绝项的产品类别分层抽查：9；
- R1 确认拒绝：9；
- 抽查误拒：0 / 9；
- 误拒率点估计：0%；
- Wilson 95% 置信区间：0.0%–29.9%。

由于抽查样本只有 9 条，论文不得把 0% 点估计表述为“AI 没有误拒”；必须同时报告较宽的置信区间。

## 4. 来源切分修正

校验发现 `espresso-005`、`espresso-015`、`espresso-016` 均来自 Scott Schiller，但原工作簿将 `espresso-016` 分到 `source_disjoint_test`，其余两条分到 `development`。

为避免同一创作者跨开发集和来源隔离测试集，导入时执行以下可审计修正：

```text
espresso-016: source_disjoint_test -> development
```

原始提交工作簿保持不变。修正记录保存在 `data_video/manifests/review_split_overrides.csv`。

修正后的 19 条接受项：

- development：13；
- source_disjoint_test：6。

## 5. 接受项类别分布

| 类别 | 本批接受 |
|---|---:|
| Air Fryer | 3 |
| Espresso Machine | 7 |
| Pressure Cooker | 0 |
| Printer | 2 |
| Vacuum | 4 |
| Washing Machine | 3 |
| **合计** | **19** |

Pressure Cooker 本批没有接受项，是下一轮数据补充的最高优先级。

## 6. 论文披露边界

论文应表述为“AI 预标注 + 一名人工复核人全量复核 AI 保留项 + 20% 分层抽查 AI 拒绝项”。可以报告 AI—R1 修正率和抽查误差，但不能报告或暗示多人标注一致性。

本批结果尚不是最终论文测试集。必须先完成增量视频筛选、来源去重、数据集冻结和 100 个检索问题的 R1 全量复核。
