# 视频授权状态记录（2026-07-16）

项目负责人已在当前项目任务中确认：现有相关视频均已取得授权，并要求直接下载。

执行边界：

- 下载现有 inventory 中 `provisional_accept`、`scope_review` 和 `hold_privacy` 状态的11条视频；
- `drill-001` 因为是机床钻孔而非手持电钻，继续保持 `reject_scope`，不下载；
- 开放许可证据仍以各 Wikimedia Commons 文件页为准；
- 项目负责人的确认作为内部下载授权记录，不替代当时执行的 A/B/C 内容、隐私和数据集划分审核；该批次为历史记录，新增数据按 2026-07-22 的 AI + R1 协议执行；
- 授权邮件、合同或其他原始证据应保存在私有授权档案中，不提交 Git；
- 下载文件只保存在 `data_video/raw/`，不提交 Git，也不在许可证不允许时重新分发。

授权引用字符串：

```text
Project owner authorization confirmation in Codex task on 2026-07-16
```

## 下载结果

- 完成时间：2026-07-16；
- 下载成功：11/11；
- 原始文件：4条；
- Wikimedia 官方视频转码：7条；
- 总字节数：131,783,571；
- 每条均生成 SHA-256；
- 11条视频均通过 FFmpeg 首帧解码；
- 原始文件保存在服务器 `~/rag3d-video/data_video/raw/authorized_sources/`；
- 下载凭证保存在 `data_video/manifests/download_receipts.csv`；
- `drill-001` 继续因产品范围不匹配而未下载。
