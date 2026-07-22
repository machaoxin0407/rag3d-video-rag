# 视频数据集扩充状态与缺口（2026-07-21）

## 1. 已冻结目标

- 产品范围：Air Fryer、Espresso Machine、Pressure Cooker、Washing Machine、Vacuum、Printer；
- 第一阶段：每类 10 条开发视频 + 3 条来源隔离测试候选，共约 78 条；
- 第二阶段：每类 15 条开放/公开来源 + 5 条 OOD，共约 120 条；
- 所有新视频先进入隔离区；只有技术、许可、AI 预标注和 R1 人工复核全部通过后，才可进入正式索引；
- 产品部署优先，论文数据和实验设计必须保留来源、许可、哈希、切分及排除原因。

## 2. 本轮实际完成

| 环节 | 结果 |
|---|---:|
| Wikimedia 候选发现 | 72 |
| Wikimedia 成功下载并生成 SHA-256 凭证 | 71 |
| Internet Archive 成功下载并生成 SHA-256 凭证 | 4 |
| 当前隔离区有凭证的视频 | 75 |
| Wikimedia 技术通过 | 64 |
| Wikimedia 技术淘汰 | 7 |
| Archive 技术通过 | 4 |
| Wikimedia VLM 保留供人工复核 | 22 |
| Wikimedia VLM 明确排除 | 42 |
| Archive VLM 保留供人工复核 | 4 |
| AI 保留项进入 R1 全量复核 | 26 |
| AI 拒绝项进入 R1 分层抽查 | 9 / 42 |
| R1 当前总复核队列 | 35 |
| 其中高风险优先复核 | 6 |
| R1 已完成 | 35 / 35 |
| R1 最终接受 | 19 |
| R1 最终拒绝 | 16 |
| AI 拒绝抽查误拒 | 0 / 9 |
| 五帧视觉近重复对（阈值 12） | 0 |

7 条技术淘汰项只因文件过小或分辨率不足；42 条内容淘汰项主要是搜索词误命中，包括航天真空试验、Hoover 人名/水坝、压力清洗机、3D 打印、动物或影片标题等。它们保留审计行，其中 9 条按固定种子和产品类别分层进入人工抽查，其余不进入正式数据池。

## 3. 当前缺口估计

下表合并初始 10 条正式视频与本轮 R1 接受的 19 条视频。第一阶段目标为每类 13 条。

| 产品类别 | 初始正式接受 | 本轮 R1 接受 | 当前合计 | 距 13 条仍缺 |
|---|---:|---:|---:|---:|
| Air Fryer | 0 | 3 | 3 | 10 |
| Espresso Machine | 3 | 7 | 10 | 3 |
| Pressure Cooker | 1 | 0 | 1 | 12 |
| Washing Machine | 3 | 3 | 6 | 7 |
| Vacuum | 2 | 4 | 6 | 7 |
| Printer | 1 | 2 | 3 | 10 |
| **合计** | **10** | **19** | **29** | **49** |

Pressure Cooker、Air Fryer 和 Printer 仍是最高优先级缺口。本批审核完成记录见 `SINGLE_REVIEWER_COMPLETION_2026-07-22.md`。

## 4. 六条高风险候选

| ID | 风险 | 建议 |
|---|---|---|
| `espresso-010` | 标题为咖啡豆气候内容，VLM 认为画面含机器操作 | 人工核对完整视频，不凭标题或稀疏帧决定 |
| `pressure-002` | 自制酒精设备改装，存在安全和产品范围风险 | 默认拒绝，除非只作为明确负样本 |
| `pressure-006` | 画面实际为热风烹饪设备，模型预测 Air Fryer | 若接受，改标为 Air Fryer OOD，不得保留 Pressure Cooker 标签 |
| `pressure-009` | 只有压力锅宣传和产品展示，没有功能步骤 | 可作为识别负载，不进入步骤检索金标准 |
| `printer-002` | UV 打印产品展示，无明确操作步骤 | 仅在需要工业打印 OOD 时保留 |
| `vacuum-026` | 真空包装机，不是家用吸尘器 | 从 Vacuum 主数据集拒绝，可留作困难负样本 |

## 5. 正在执行的下载队列

7 个已授权 Internet Archive 任务中，4 个已经下载落盘：

- Air Fryer：`airfryer-002`、`airfryer-008`；
- Pressure Cooker：`pressure-010`、`pressure-017`。

3 个仍在 Windows BITS 可续传队列：

- Air Fryer：`airfryer-005`；
- Pressure Cooker：`pressure-011`、`pressure-012`。

7 条全部仍需登记、哈希、技术筛选和 AI 内容筛选；只有通过筛选的条目才进入增量 R1 复核包。

Archive CDN 当前吞吐较低且偶发 HTTP 500。任务使用可续传方式，不绕过访问控制，也不把未完成文件计入数据集规模。

## 6. AI + 单人复核入口

审核清单为 `data_video/manifests/candidate_review_queue.csv`：

1. R1 已全量复核 26 条 `full_positive_review`；
2. R1 已复核 9 条 `rejected_audit_sample`，9 条均确认拒绝；
3. R1 打开来源页并查看完整视频，填写许可证据状态、修正类别/过程/功能步骤、隐私与安全风险、修正原因、最终决定和复核时间；
4. 只有 `review_status=completed`、`license_evidence_status=verified` 且 `final_decision=accept` 的视频才允许迁移到正式清单；
5. 抽查发现 AI 误拒时，将该条改为 `accept` 并按完整接受项标准补齐字段；
6. 来源隔离测试候选不得与开发集共享相同创作者、上传账户或同一原始视频变体。

## 7. 后续执行顺序

1. 完成 7 个 BITS 下载并运行同一套登记、技术和 VLM 筛选；
2. 将本轮 19 条接受项迁移到正式清单，并保留 16 条拒绝项作为审计记录；
3. 继续定向补 Pressure Cooker、Air Fryer 和 Printer；普通网页搜索不再直接批量下载，先验证类别和许可证；
4. 将最终接受项合并到 `video_source_inventory.csv`、`download_receipts.csv` 和 `review_assignments.csv`；
5. 对接受项依次执行预处理、场景切分、ASR/OCR/VLM、证据构建和三路检索索引；
6. R1 冻结开发/来源隔离测试切分，并全量复核 100 个问题的相关性与时间边界后，才启动论文主实验。

## 8. 论文使用边界

- 论文数据规模只统计最终经 R1 复核接受的条目，不统计 75 条隔离下载；
- 42 条错域视频可以构成“查询歧义/困难负样本”附加实验，但不能冒充目标类正样本；
- `pressure-006` 这类模型发现的类别错误应计入数据清洗错误分析；
- 论文必须分别报告技术淘汰、AI 内容淘汰、许可淘汰和最终接受数量，避免选择性报告；
- 论文明确写明 AI 辅助标注和单人复核，报告修正率及拒绝抽查误拒率，不报告不存在的多人一致性。
