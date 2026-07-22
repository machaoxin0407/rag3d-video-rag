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

四条接受项已提升到正式清单。正式接受视频共 34 条，其中六个目标产品类别共 33 条，另有 1 条兼容性相机记录。六类分布为：

| 产品类别 | 正式接受数 | 第一阶段目标 | 仍缺 |
|---|---:|---:|---:|
| Air Fryer | 5 | 13 | 8 |
| Espresso Machine | 10 | 13 | 3 |
| Pressure Cooker | 3 | 13 | 10 |
| Printer | 3 | 13 | 10 |
| Vacuum | 6 | 13 | 7 |
| Washing Machine | 6 | 13 | 7 |
| **合计** | **33** | **78** | **45** |

开发集与来源隔离测试集之间未发现创作者交叉，也未发现重复来源 URL。

## 4. 后续状态

- 34 条正式视频已完成预处理并进入场景、ASR、OCR、VLM 和证据构建流水线；
- `pressure-012` 已下载、哈希、技术检查和 AI 预标注通过，单独进入一条 R1 复核包；
- `pressure-012` 未经 R1 最终接受前，不计入正式数据集规模或论文主实验。

## 5. 论文报告边界

- 本批明确报告为 AI 辅助预标注加单人 R1 复核；
- 两条 AI 拒绝审计未发现误拒，但样本量只有 2，不能据此声称误拒率为零；
- 本批拒绝审计误拒率的 Wilson 95% 置信区间为 0–65.8%；
- 不报告不存在的多人一致性指标。
