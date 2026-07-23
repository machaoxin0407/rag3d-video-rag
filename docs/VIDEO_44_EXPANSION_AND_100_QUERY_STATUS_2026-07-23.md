# 剩余 44 条视频与 100 问题相关性集执行状态（2026-07-23）

## 1. 固定目标

论文主数据集只统计以下六类，每类目标 13 条，共 78 条：

| 产品类 | 既有基线 | 目标 | 新增缺口 |
|---|---:|---:|---:|
| Air Fryer | 5 | 13 | 8 |
| Espresso Machine | 10 | 13 | 3 |
| Pressure Cooker | 4 | 13 | 9 |
| Printer | 3 | 13 | 10 |
| Vacuum | 6 | 13 | 7 |
| Washing Machine | 6 | 13 | 7 |
| 合计 | 34 | 78 | 44 |

`camera-001` 等兼容性记录不计入六类论文数据集。新增 44 指经过 AI 预筛、R1 人工复核并正式晋升的 44 条，不是简单下载 44 个文件。

## 2. 已完成工作

### 2.1 扩展候选

- Internet Archive 候选清单：157 条；
- 技术检查：149 条通过、8 条失败；
- Qwen3-VL 内容预筛：123 条保留、25 条拒绝、1 条人工检查；
- R1 扩展工作簿：121/121 条已完成；
- 严格导入结果：74 条接受、47 条拒绝、0 条待定；
- 所有接受项均经过许可、产品类别、功能步骤、隐私、安全和切分检查。

R1 审核工作簿原始 SHA-256：

```text
1256DAB81C6F86EFAB7415CCB52402179C240594281A6BA98043589D5D459CD2
```

规范化仅为 45 条拒绝项补写了可推导的 `correction_reason`，原始工作簿没有被改写。规范化日志：

```text
data_video/manifests/r1_expansion_normalization_log_20260723.csv
```

### 2.2 确定性选择

`select_r1_expansion_promotions.py` 按以下顺序确定性选择正式晋升项：

1. 精确满足各类缺口；
2. 优先保留 `source_disjoint_test`；
3. 隐私和安全风险优先为 `none`；
4. 优先 AI–R1 一致项；
5. 平衡过程类型和作者来源；
6. 禁止与既有基线或已选项重复来源 URL；
7. 最后以 `record_id` 稳定排序。

当前已从 121 条中选定 43 条：

| 产品类 | 已选新增 | 选择后总数 | 剩余缺口 |
|---|---:|---:|---:|
| Air Fryer | 8 | 13 | 0 |
| Espresso Machine | 2 | 12 | 1 |
| Pressure Cooker | 9 | 13 | 0 |
| Printer | 10 | 13 | 0 |
| Vacuum | 7 | 13 | 0 |
| Washing Machine | 7 | 13 | 0 |
| 合计 | 43 | 77 | 1 |

43 条晋升清单已通过 `promote_single_reviewer_candidates.py --dry-run`，结果为：

```text
promoted=43 formal_inventory=79 formal_receipts=78 formal_reviews=79 dry_run=True
```

正式清单和审计文件：

```text
data_video/manifests/candidate_review_queue_expansion_completed_20260723.csv
data_video/manifests/single_reviewer_audit_summary_expansion_20260723.csv
data_video/manifests/r1_expansion_selected_43_pending_espresso_20260723.csv
data_video/manifests/r1_expansion_selection_audit_20260723.csv
data_video/manifests/r1_expansion_selection_summary_20260723.json
```

未选中的 31 条合格项保留为备用池，没有删除。

## 3. 唯一剩余视频缺口

原 121 条中 Espresso Machine 只有 2 条通过 R1，因此不能通过降低标准凑足 3 条。

已新增下载 4 条 Pexels Espresso 候选：

| 记录 | 技术检查 | AI 内容预筛 | 处理 |
|---|---|---|---|
| espresso-039 | 通过 | 拒绝：整机不可见 | 不进入 R1 |
| espresso-040 | 通过 | 保留：整机和手柄操作可见 | 首选，待 R1 |
| espresso-041 | 通过 | 保留：装入手柄步骤可见 | 备用 |
| espresso-042 | 通过 | 保留：萃取过程可见 | 备用 |

首选 `espresso-040`：

- 8.642 秒；
- 2160×3840；
- SHA-256：`9359fc489fc0eca410cb303612f5a843e2db9e708c8a8cc82afb8e4b18b88ce7`；
- Pexels 来源和许可页已记录；
- 技术检查通过；
- Qwen3-VL 判定 `retain_for_human_review`；
- 仅手臂可见，无可识别人脸。

单条 R1 复核包：

```text
C:\Users\MAXS\Desktop\single_reviewer_bundle_espresso_gap_20260723
```

复核工作簿：

```text
C:\Users\MAXS\Desktop\single_reviewer_bundle_espresso_gap_20260723\R1_video_review_workbook.xlsx
```

只需完整播放 `espresso-040`，并填写 `Review_Form` 黄色 S–AD 列。

如果 R1 接受，将形成精确新增 44 条和六类各 13 条。若 R1 拒绝，则依次启用 `espresso-041`、`espresso-042`，不降低标准。

## 4. 100 问题设计

`data_video/manifests/paper_video_queries_v1.csv` 已固定 100 个自包含问题：

- 产品分布：17 / 17 / 17 / 17 / 16 / 16；
- 语言：中文 50、英文 50；
- 切分：development 60、source_disjoint_test 40；
- 类型：operation 18、state 18、component 18、maintenance 18、troubleshooting 16、safety 12；
- 无重复问题；
- 每个问题只能路由到一个预期产品类；
- 不包含来源标题、作者、型号或逐字转录泄漏。

当前状态：

```text
design_frozen_pending_final_78_video_index
```

## 5. 完成第 44 条后的自动流水线

1. 严格导入单条 R1 结果；
2. 合并 43+1 条晋升队列；
3. 实际执行晋升，冻结 78 条六类正式视频；
4. 校验来源隔离、SHA-256、许可、隐私、安全和类别计数；
5. 在服务器重建：
   - 视频预处理与关键帧；
   - 场景切分；
   - ASR；
   - OCR；
   - Qwen3-VL 场景描述；
   - 视频证据清单；
   - 文本稠密索引；
   - Qwen3-VL 直接视觉索引；
6. 对 100 问题分别运行 BM25、dense、visual、hybrid、tri_hybrid 五路 top-20；
7. 合并去重并生成盲审候选池；
8. 生成 AI 相关性预标注；
9. 生成正式 R1 相关性工作簿；
10. 完成论文级数据版本、运行清单、统计检验和可复现实验报告。

## 6. 论文口径

- 可以报告“AI 预标注 + 单名人工复核”；
- 不能把单名人工复核写成标注员间一致性；
- 应报告 AI–R1 一致率、人工修正率、拒绝抽查的假阴性率及 Wilson 区间；
- 最终相关性等级固定为 0–3；
- 只有在 78 条视频、五路候选池、100 问题相关性和时间边界全部冻结后，才能称为论文正式 v1 金标准。

## 7. 当前阻塞点

唯一必要输入是 `espresso-040` 的一行 R1 复核结果。服务器两张 RTX 4090 已释放，当前无项目 GPU 进程。
