# 单人视频复核包操作指南

## 生成复核包

在服务器仓库根目录运行：

```bash
.venv/bin/python prepare_single_reviewer_bundle.py \
  --technical-screen data_video/manifests/candidate_technical_screen.csv \
  --technical-screen data_video/manifests/archive_candidate_technical_screen.csv
```

默认输出目录：

```text
data_video/review/single_reviewer_bundle/
```

视频和采样帧优先创建硬链接，不重复占用磁盘空间。若文件系统不支持硬链接，脚本才会复制。重新运行不会删除已有文件，也不会覆盖已经填写过的 `review_form.csv`。

## 目录结构

```text
single_reviewer_bundle/
  README.md
  index.html
  review_form.csv
  source_queue_snapshot.csv
  bundle_manifest.csv
  items/
    espresso-010/
      video.webm
      frames/sample_01.jpg ... sample_05.jpg
    ...
```

## R1 的具体操作

1. 下载整个 `single_reviewer_bundle` 目录，或者在服务器文件共享中直接打开；不能只下载 CSV。
2. 用 Chrome、Edge 或 Firefox 打开 `index.html`。
3. 按 `high → normal → audit` 的顺序复核。
4. 每条视频必须完整播放一次；五张采样帧仅用于快速回看。
5. 点击来源链接，核对创作者、许可证及授权范围。
6. 用 Excel 或 LibreOffice 打开 `review_form.csv`，不要排序后只保存部分行，不要修改 `record_id` 和 `ai_*` 字段。
7. 只填写下列人工字段：
   - `review_status`；
   - `license_evidence_status`；
   - `corrected_product_class`；
   - `corrected_procedure_relevance`；
   - `corrected_functional_step_visible`；
   - `privacy_risk`；
   - `safety_risk`；
   - `correction_reason`；
   - `final_decision`；
   - `dataset_split`；
   - `reviewed_at`。
8. 每完成一行，将 `review_status` 改为 `completed`。不确定项用 `hold`，不要猜测。
9. 保存为 UTF-8 CSV，文件名保持 `review_form.csv`。
10. 全部完成后通知项目维护者；维护者执行枚举、必填字段、重复 ID、来源切分和哈希校验，再导入正式 manifest。

字段取值、抽查制度和论文写法以 [AI_SINGLE_REVIEWER_ANNOTATION_PROTOCOL_2026-07-22.md](./AI_SINGLE_REVIEWER_ANNOTATION_PROTOCOL_2026-07-22.md) 为准。

## 新下载视频如何加入

新下载完成后必须先执行登记、SHA-256、技术筛选和 AI 内容筛选，再重新生成 `candidate_review_queue.csv`。之后再次运行本页的复核包命令即可把新增条目放进同一目录。

若 `review_form.csv` 已经包含人工填写内容，脚本不会覆盖它。此时应先备份并导入已完成结果，再由维护者生成包含新增记录的新版本；不要使用 `--refresh-form` 强制覆盖人工结果。
