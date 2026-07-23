# 剩余 44 条视频与 100 问题相关性集执行状态（2026-07-23）

## 1. 固定目标

论文主数据集只统计以下六类，每类目标 13 条，共 78 条：

| 产品类 | 当前正式条数 | 目标 | 净缺口 |
|---|---:|---:|---:|
| Air Fryer | 5 | 13 | 8 |
| Espresso Machine | 10 | 13 | 3 |
| Pressure Cooker | 4 | 13 | 9 |
| Printer | 3 | 13 | 10 |
| Vacuum | 6 | 13 | 7 |
| Washing Machine | 6 | 13 | 7 |
| 合计 | 34 | 78 | 44 |

`camera-001` 仅保留为兼容性记录，不计入六类论文数据集。净增 44 指完成 AI 预筛、R1 人工复核并正式接受的 44 条，而不是下载 44 个文件。

## 2. 候选发现和下载状态

- 第一轮从 Internet Archive 搜索结果中解析 292 条候选元数据，选择 95 条；针对 Vacuum 和 Washing Machine 的缺口又解析 201 条，选择 41 条；并重试历史种子；
- 最终成功下载并登记 157 条候选，每条均保留来源页、直接文件 URL、授权引用、文件字节数、SHA-256 和响应回执；
- 技术筛查覆盖 157/157：149 条通过、8 条失败；每条通过项抽取 5 帧；
- Qwen3-VL 内容预筛覆盖 149/149：123 条 `retain_for_human_review`、25 条 `reject_out_of_scope`、1 条 `manual_review`；
- R1 扩展复核队列共 121 条：115 条 AI 正向候选全量复核，另有 6 条 AI 拒绝项分层抽查；
- 元数据和 AI 预筛都不替代 R1。正式净增 44 条只能从 R1 接受项中按类别缺口和来源隔离规则晋升。

关键产物：

- `data_video/manifests/archive_discovery_20260723.csv`：292 条发现与文件选择证据；
- `data_video/manifests/archive_discovery_targeted_20260723.csv`：201 条定向补充发现记录；
- `data_video/manifests/archive_candidate_seeds_20260723.csv`：95 条新下载种子；
- `data_video/manifests/archive_candidate_seeds_targeted_20260723.csv`：41 条定向补充种子；
- `data_video/manifests/archive_candidate_download_receipts.csv`：157 条下载回执；
- `data_video/manifests/archive_candidate_technical_screen.csv`：157 条技术筛查结果；
- `data_video/manifests/archive_candidate_content_screen.csv`：149 条 AI 内容筛查结果；
- `data_video/manifests/candidate_review_queue_expansion_20260723.csv`：121 条盲化人工复核队列；
- `discover_archive_video_candidates.py`：可复现发现脚本；
- `download_archive_video_candidates.py`：下载、哈希和回执脚本。

## 3. 新视频的固定处理链

1. 下载并写入 SHA-256、来源页、直接文件 URL、授权引用和下载时间；
2. `screen_video_candidates.py` 检查可解码性、时长、分辨率、音轨、重复文件并抽取 5 帧；
3. `classify_video_candidates.py` 用固定 Qwen3-VL 模型、revision 和提示词生成 AI 预标注；
4. `prepare_candidate_review_queue.py` 将 AI 保留项全部加入 R1，AI 拒绝项按产品分层固定种子抽查 20%；
5. `prepare_single_reviewer_bundle.py` 生成一个文件夹，包含完整视频、采样帧、来源链接、HTML 导航页和 Excel 标注表；
6. R1 完成后运行严格导入校验；只有 `completed + verified + accept + 非 excluded 切分` 才能晋升；
7. 若某类不足 13，继续发现和筛查下一批候选，绝不降低类别、功能步骤、隐私、安全或许可标准来凑数；
8. 达到 78 条后冻结来源隔离切分，重新运行场景切分、ASR、OCR、VLM 描述、证据合并、文本稠密索引和视觉索引。

## 4. 100 问题设计冻结

`data_video/manifests/paper_video_queries_v1.csv` 已固定 100 个自包含问题：

- 产品分布：17 / 17 / 17 / 17 / 16 / 16；
- 语言分布：`zh-CN` 50、`en` 50；
- 切分：development 60、source_disjoint_test 40；
- 类型：operation 18、state 18、component 18、maintenance 18、troubleshooting 16、safety 12；
- 无重复问题；
- 不包含来源标题、作者、型号或逐字转录引用；
- 每个问题均能被产品路由器唯一识别为预期产品类；已补齐 Air Fryer 路由别名。

当前状态为 `design_frozen_pending_index_validation`。这表示项目内设计已冻结，但尚未声称完成外部平台预注册。最终索引建立后允许的唯一问题集修改，是在盲态可回答性检查中替换“整个语料没有任何相关场景”的问题；每次替换必须保留版本、原因和时间戳，且不得查看被比较方法的测试集成绩。

工作簿 `outputs/20260723-video-expansion/paper_video_query_design_v1.xlsx` 包含 README、100 问题、公式化覆盖检查和最终相关性字段结构。覆盖页当前 17 项均为 PASS。

## 5. 正式相关性候选池

最终索引冻结后运行 `pool_video_relevance_candidates.py`：

```powershell
python pool_video_relevance_candidates.py `
  --top-k-per-mode 20 `
  --modes bm25 dense visual hybrid tri_hybrid `
  --dense-endpoint http://127.0.0.1:8011/embed `
  --visual-endpoint http://127.0.0.1:8012/embed `
  --require-all-modes
```

对每个问题分别从五种检索方式取前 20 个场景，合并去重并用固定种子打乱。审计文件保存方法、排名和分数；盲审文件不包含这些信息。R1 在看不到算法身份、排名和分数的条件下复核所有合并候选。

正式字段为：

```text
query_id, query_text, product_class, query_type, split,
candidate_scene_id, ai_relevance_grade, ai_start_time, ai_end_time,
ai_evidence, ai_uncertainty,
r1_relevance_grade, r1_start_time, r1_end_time,
r1_source_leakage, correction_reason, review_status, reviewed_at
```

相关性固定为 0–3：0 不相关；1 仅背景或同产品相关；2 部分回答或相邻步骤；3 直接回答且有视觉、ASR 或 OCR 证据。

## 6. 何时可以称为“论文正式相关性标注集”

以下条件全部满足后才可冻结 v1 金标准：

1. 六类各 13 条视频均由 R1 接受；
2. 来源隔离切分无同上传者、同视频或近重复泄漏；
3. 最终场景、证据、文本索引和视觉索引的哈希写入 run manifest；
4. 五路候选池完成且没有稠密/视觉方式静默回退；
5. AI 预标注保留模型、revision、提示词、原始输出和运行时间；
6. R1 完成全部问题—候选对的相关性、时间边界与来源泄漏复核；
7. 每个问题至少存在一个 R1 标为 2 或 3 的场景；无法回答的问题按冻结规则替换并留痕；
8. 盲审表和含排名审计表通过 ID、数量、时间范围、枚举值和重复项校验；
9. 论文只报告 AI–R1 一致率和人工修正率，不把单人复核写成标注员间一致性。

## 7. 当前阻塞点

下载、技术筛查、AI 预标注、R1 队列、复核文件夹和 100 问题设计均已完成。当前唯一必要输入是 R1 对 121 条队列的人工复核结果。复核工作簿位于：

`C:\Users\MAXS\Desktop\single_reviewer_bundle_expansion_20260723\R1_video_review_workbook.xlsx`

R1 完成后执行以下收尾链：

1. 严格校验工作簿枚举值、必填项、时间戳、许可核验和决定一致性；
2. 按缺口 8 / 3 / 9 / 10 / 7 / 7 晋升恰好 44 条，并保留未晋升的合格项作为备用；
3. 冻结 78 条正式视频和来源隔离切分，重新生成场景、ASR、OCR、VLM 和全部索引；
4. 对 100 问题运行五路 top-20 候选池，生成盲审表与排名审计表；
5. AI 预标注问题—场景相关性后，由同一 R1 复核，完成 v1 金标准冻结。

在第 2 步完成前，不能声称“44 条正式视频已补齐”；在第 5 步完成前，不能声称“100 问题相关性金标准已完成”。这是论文审计边界，不是技术阻塞。

## 8. 可复现验证

以下命令已在 2026-07-23 完整执行并返回 `status=PASS`，包括 157 个原视频和 121 个复核视频的 278 次 SHA-256 核验、605 张采样帧、清单集合关系、类别覆盖及 100 问题路由检查：

```powershell
python validate_video_expansion_release.py `
  --bundle-dir "C:\Users\MAXS\Desktop\single_reviewer_bundle_expansion_20260723" `
  --verify-hashes
```
