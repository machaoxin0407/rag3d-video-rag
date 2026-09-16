# 视频预处理基线（2026-07-17）

## 执行版本

- Git 分支：`agent/environment-baseline`；
- 预处理代码提交：`15264d8`；
- 服务器项目：`~/rag3d-video`；
- FFmpeg：`7.0.2-static`；
- 关键帧间隔：5 秒；
- 执行设备：CPU，未申请 GPU。

## 验收结果

| 指标 | 结果 |
|---|---:|
| A/B/C 最终接受视频 | 11 |
| 成功处理 | 11 |
| 失败 | 0 |
| 总视频时长 | 784.28 秒 |
| 帧率有效记录 | 11/11 |
| 已提取 16 kHz 单声道音频 | 11/11 |
| 均匀关键帧 | 156 张 |
| 原始视频占用 | 126 MB |
| 处理音频目录占用 | 25 MB |
| 关键帧目录占用 | 11 MB |

每条源视频均在处理前重新计算 SHA-256，并与 `download_receipts.csv` 交叉验证。最终清单中的 11 条源哈希全部一致，路径均为项目内相对路径。

## 数据边界说明

服务器的 `data_video/processed/` 和 `data_video/keyframes/` 还保留第一周环境检查产生的 `week01_smoke` 测试产物。遵循“不清理”要求，本次未删除它们。因此：

- 本阶段统计只以 `preprocessing_manifest.csv` 为准；
- 后续 ASR、OCR、镜头切分与索引程序必须从 manifest 读取 11 条正式记录；
- 禁止通过递归遍历整个媒体目录来推断正式数据集规模。

## 下一阶段入口

后续流水线可以直接使用：

- 音频：`data_video/processed/<record_id>/audio_16k_mono.wav`；
- 帧证据：`data_video/keyframes/<record_id>/frame_*.jpg`；
- 源级元数据：`data_video/manifests/preprocessing_manifest.csv`。

下一步优先实现离线 ASR、OCR 和基于镜头边界的视频片段清单，再把文本、手册图片和视频时间段统一映射为同一种证据对象。
