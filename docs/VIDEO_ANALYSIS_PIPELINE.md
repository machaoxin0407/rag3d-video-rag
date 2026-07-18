# 视频内容分析与统一证据流水线

本阶段把已通过审核和预处理的 11 条视频转换为可检索的时间轴证据。流水线严格从 manifest 读取数据，不遍历整个媒体目录，因此不会纳入 `week01_smoke` 等环境测试文件。

## 产物关系

```text
preprocessing_manifest.csv
  ├─ FFmpeg 场景检测与 MP4 片段 ─> scene_manifest.csv
  ├─ faster-whisper large-v3 ───> asr_runs.csv + asr_segments.csv
  └─ PaddleOCR 关键帧识别 ──────> ocr_runs.csv + ocr_observations.csv

scene + ASR + OCR
  └─ build_video_evidence.py ────> video_evidence_manifest.csv
```

最终证据清单包含三种对象：

- `video_scene`：可直接播放的视频片段，文本由重叠的 ASR 与 OCR 聚合而成；
- `speech_segment`：带词级时间戳和语言置信度的语音证据，并链接到所属视频片段；
- `frame_text`：带位置多边形和置信度的画面文字证据，并链接关键帧及所属视频片段。

每个对象都保留源视频 SHA-256。视频片段还单独记录片段 SHA-256，便于产品响应和论文实验复核。

## 隔离环境

现有 `.venv` 继续负责手册 RAG、FFmpeg 和镜头切分。ASR 与 OCR 使用两个短生命周期隔离环境，防止 PaddlePaddle、CTranslate2 和现有 PyTorch 的 CUDA 依赖互相覆盖。

```bash
cd ~/rag3d-video

python3 -m virtualenv .venv-asr
.venv-asr/bin/pip install -r requirements-asr.txt

python3 -m virtualenv .venv-ocr
.venv-ocr/bin/pip install -r requirements-ocr.txt
```

模型缓存保存在已忽略的 `models/`，不进入 Git。

## 1. 镜头检测与片段

```bash
.venv/bin/python segment_video_sources.py \
  --threshold 0.32 \
  --minimum-scene-seconds 2
```

FFmpeg 的场景变化分数用于生成边界。每个片段转为 H.264/AAC MP4，并启用 `faststart`，可直接供浏览器或 API 以时间片段证据返回。

## 2. 离线 ASR

`faster-whisper` 的 GPU 运行需要 CUDA 12 的 cuBLAS 与 cuDNN 9。依赖已安装在 `.venv-asr` 内，启动前只把该环境的动态库加入当前命令：

```bash
ASR_LIBS=$(.venv-asr/bin/python -c 'import os; import nvidia.cublas.lib; import nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))')

LD_LIBRARY_PATH="$ASR_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  .venv-asr/bin/python transcribe_video_sources.py \
  --model large-v3 \
  --device cuda \
  --device-index 0 \
  --compute-type float16 \
  --beam-size 5
```

每条记录启用 VAD、段级时间戳和词级时间戳。进程退出后 GPU 显存会释放；不启动 ASR 常驻服务。

## 3. 关键帧 OCR

```bash
.venv-ocr/bin/python ocr_video_keyframes.py \
  --language-profile de \
  --ocr-version PP-OCRv5 \
  --device cpu \
  --minimum-score 0.50
```

`de` 在 PP-OCRv5 中选择覆盖德语、葡萄牙语、英语等语言的 Latin 多语识别模型。当前只有 156 张关键帧，CPU 模式更易部署且不会引入第二套 CUDA 运行时。

## 4. 统一证据清单

```bash
.venv/bin/python build_video_evidence.py
```

构建程序要求 11 条记录的场景、ASR 和 OCR source-level run 全部成功，否则拒绝输出最终证据清单。ASR 段和 OCR 观察项通过时间戳关联到具体场景片段。

## 验收原则

1. 11 条视频均有连续、无越界的场景覆盖；
2. 每个生成片段存在、可解码，且 SHA-256 与清单相符；
3. ASR 与 OCR run 均为 11/11 成功；
4. 所有语音段和 OCR 时间戳都能映射到一个场景；
5. 统一证据 ID 全局唯一，所有媒体路径均为项目内相对路径；
6. ASR 进程退出后无项目 GPU 进程残留。

## 当前边界

当前 `video_scene` 的文本仅融合 ASR 与 OCR。没有语音、也没有可识别屏幕文字的纯视觉片段可能暂时为空文本；下一阶段需要增加 VLM 场景 caption，随后才能完成视觉语义召回和跨模态重排。
