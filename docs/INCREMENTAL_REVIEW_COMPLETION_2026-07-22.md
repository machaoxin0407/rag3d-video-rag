# 增量视频复核完成记录（2026-07-22）

## 1. 输入与方法

- 输入工作簿：`single_reviewer_bundle_incremental_20260722_6items/R1_video_review_workbook.xlsx`；
- 复核协议：`ai_single_reviewer_v1`；
- AI 模型：Qwen3-VL-8B-Instruct，五帧稀疏视觉预标注；
- 人工复核者：R1；
- 所有 6 条记录均查看完整视频、来源页面与许可证据；
- 标注工作簿原件保留，导入时只把人工字段写入规范 CSV。

## 2. 复核结果

| 指标 | 结果 |
|---|---:|
| 完成 | 6 / 6 |
| 最终接受 | 4 |
| 最终拒绝 | 2 |
| 暂缓 | 0 |
| AI 保留项最终接受 | 4 / 4 |
| AI 拒绝抽查误拒 | 0 / 2 |
| AI 产品类别修正 | 0 / 4 |
| AI 过程相关性修正 | 0 / 4 |
| AI 功能步骤修正 | 0 / 4 |

接受项：

- `airfryer-002`：Air Fryer，development；
- `airfryer-005`：Air Fryer，source_disjoint_test；
- `pressure-010`：Pressure Cooker，development；
- `pressure-011`：Pressure Cooker，source_disjoint_test。

拒绝项：

- `airfryer-008`：只有产品推荐口播，未出现实物操作步骤；
- `pressure-017`：游戏录屏，与真实压力锅操作无关。

## 3. 数据集影响

本批四条接受项与随后完成复核的 `pressure-012` 均已提升到正式清单。可分析视频共 35 条，其中六个目标产品类别共 34 条，另有 1 条兼容性相机记录。六类分布为：

| 产品类别 | 正式接受数 | 第一阶段目标 | 仍缺 |
|---|---:|---:|---:|
| Air Fryer | 5 | 13 | 8 |
| Espresso Machine | 10 | 13 | 3 |
| Pressure Cooker | 4 | 13 | 9 |
| Printer | 3 | 13 | 10 |
| Vacuum | 6 | 13 | 7 |
| Washing Machine | 6 | 13 | 7 |
| **合计** | **34** | **78** | **44** |

开发集与来源隔离测试集之间未发现创作者交叉，也未发现重复来源 URL。

## 4. 后续状态

- 35 条正式视频已完成预处理、场景切分、ASR、OCR、VLM 和统一证据构建；
- 全分析校验通过：256 个场景、348 条语音片段、1,464 条 OCR 观测、256 条 VLM 场景描述，共 2,068 条证据，场景空文本为 0；
- 文本稠密索引已覆盖 256 个场景（Qwen3-Embedding-0.6B，1,024 维）；
- 直接视频视觉索引已覆盖 256 个场景（Qwen3-VL-Embedding-2B，2,048 维）；
- R1 已接受 `pressure-012` 并冻结到 `source_disjoint_test`；许可证、过程相关性、功能步骤、隐私与安全字段均通过导入校验；
- Internet Archive 上传者标识采用 SHA-256 截断假名保存；规范化后跨集合创作者冲突和重复来源 URL 均为 0。

## 5. 临时检索回归结果（2026-07-23）

以下结果只基于 9 条开发期种子问题，用于确认检索组件真实工作，不是论文正式指标：

| 模式 | Hit@1 | Hit@3 | MRR@3 |
|---|---:|---:|---:|
| BM25 | 55.6% | 77.8% | 66.7% |
| Text dense | 66.7% | 77.8% | 72.2% |
| Direct video visual | 88.9% | 100.0% | 94.4% |
| BM25 + text dense | 66.7% | 77.8% | 72.2% |
| BM25 + text dense + visual | 66.7% | 88.9% | 75.9% |

强制模式检查确认没有静默退回 BM25；加入 `pressure-012` 后，上表指标保持不变。原始结果保存在 `reports/video_retrieval_incremental_20260723.json`，增量后结果保存在 `reports/video_retrieval_pressure012_20260723.json`。

## 6. 论文报告边界

- 本批明确报告为 AI 辅助预标注加单人 R1 复核；
- 两条 AI 拒绝审计未发现误拒，但样本量只有 2，不能据此声称误拒率为零；
- 本批拒绝审计误拒率的 Wilson 95% 置信区间为 0–65.8%；
- 9 条种子问题仅作工程回归，不进入论文主结果；论文主结果仍需完成预注册的 100 问题单人相关性复核；
- 不报告不存在的多人一致性指标。
