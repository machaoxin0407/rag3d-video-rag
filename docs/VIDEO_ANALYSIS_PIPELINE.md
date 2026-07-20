# 视频内容分析与统一证据流水线

本阶段把已通过审核和预处理的 11 条视频转换为可检索的时间轴证据。流水线严格从 manifest 读取数据，不遍历整个媒体目录，因此不会纳入 `week01_smoke` 等环境测试文件。

## 产物关系

```text
preprocessing_manifest.csv
  ├─ FFmpeg 场景检测与 MP4 片段 ─> scene_manifest.csv
  ├─ faster-whisper large-v3 ───> asr_runs.csv + asr_segments.csv
  ├─ PaddleOCR 关键帧识别 ──────> ocr_runs.csv + ocr_observations.csv
  └─ Qwen3-VL 场景多帧描述 ─────> vlm_runs.csv + vlm_scene_captions.csv

scene + ASR + OCR + VLM
  └─ build_video_evidence.py ────> video_evidence_manifest.csv

video_evidence_manifest.csv
  ├─ BM25 场景词法索引
  └─ Qwen3-Embedding-0.6B ───────> 1024 维场景向量

BM25 rank + dense rank
  └─ 加权 RRF ───────────────────> 文字答案 + 手册图片 + 视频片段
```

最终证据清单包含三种对象：

- `video_scene`：可直接播放的视频片段，文本由重叠的 ASR 与 OCR 聚合而成；
- `speech_segment`：带词级时间戳和语言置信度的语音证据，并链接到所属视频片段；
- `frame_text`：带位置多边形和置信度的画面文字证据，并链接关键帧及所属视频片段。

每个对象都保留源视频 SHA-256。视频片段还单独记录片段 SHA-256，便于产品响应和论文实验复核。

## 隔离环境

现有 `.venv` 继续负责手册 RAG、FFmpeg 和镜头切分。ASR、OCR、VLM 与视频稠密检索使用四个隔离环境，防止 PaddlePaddle、CTranslate2 和 PyTorch 的 CUDA 依赖互相覆盖。

```bash
cd ~/rag3d-video

python3 -m virtualenv .venv-asr
.venv-asr/bin/pip install -r requirements-asr.txt

python3 -m virtualenv .venv-ocr
.venv-ocr/bin/pip install -r requirements-ocr.txt

./setup_video_vlm_environment.sh
./setup_video_embedding_environment.sh
```

模型缓存保存在已忽略的 `models/`，不进入 Git。

## 1. 镜头检测与片段

```bash
./run_video_analysis_stage.sh scenes
```

FFmpeg 的场景变化分数用于生成边界。每个片段转为 H.264/AAC MP4，并启用 `faststart`，可直接供浏览器或 API 以时间片段证据返回。

## 2. 离线 ASR

`faster-whisper` 的 GPU 运行需要 CUDA 12 的 cuBLAS 与 cuDNN 9。依赖已安装在 `.venv-asr` 内，启动前只把该环境的动态库加入当前命令：

```bash
./run_video_analysis_stage.sh asr
```

服务器当前无法直接访问 `huggingface.co`，包装脚本默认把 `HF_ENDPOINT` 设为 `https://hf-mirror.com`，仅用于下载公开模型文件；同时设置 `HF_HUB_DISABLE_XET=1`，防止客户端绕过镜像访问 Xet/CAS。直接连接恢复后可以在命令前显式覆盖这些变量。

每条记录启用 VAD、段级时间戳和词级时间戳。进程退出后 GPU 显存会释放；不启动 ASR 常驻服务。

## 3. 关键帧 OCR

```bash
./run_video_analysis_stage.sh ocr
```

`de` 在 PP-OCRv5 中选择覆盖德语、葡萄牙语、英语等语言的 Latin 多语识别模型。当前只有 156 张关键帧，CPU 模式更易部署且不会引入第二套 CUDA 运行时。

## 4. 离线 VLM 场景描述

```bash
./run_video_analysis_stage.sh vlm
```

VLM 阶段使用 `Qwen/Qwen3-VL-8B-Instruct`，为每个场景在内部时间点抽取 1–3 张审计帧，并生成中英文摘要、可见产品、部件、动作、状态、安全文字与不确定性。产品清单类别只用于通用设备类别消歧，不允许据此推断型号、规格或不可见动作。

输出默认标记为 `review_status=pending`。模型描述可以进入实验检索索引，但不能当作人工金标准；三人标注团队仍需按 `docs/VIDEO_VLM_CAPTION_BASELINE_2026-07-20.md` 中的队列优先级复核。

## 5. 统一证据清单

```bash
./run_video_analysis_stage.sh evidence
```

构建程序要求 11 条记录的场景、ASR、OCR 以及 25 个场景的 VLM run 全部成功，否则拒绝输出最终证据清单。ASR 段和 OCR 观察项通过时间戳关联到具体场景片段，VLM 描述按 `scene_id` 一对一融合。

## 验收原则

1. 11 条视频均有连续、无越界的场景覆盖；
2. 每个生成片段存在、可解码，且 SHA-256 与清单相符；
3. ASR 与 OCR run 均为 11/11 成功，VLM run 为 25/25 成功；
4. 所有语音段和 OCR 时间戳都能映射到一个场景；
5. 统一证据 ID 全局唯一，所有媒体路径均为项目内相对路径；
6. VLM 帧路径、结构化 JSON、模型修订号和提示词版本均有效；
7. ASR/VLM 进程退出后无项目 GPU 进程残留。
8. dense 索引的场景顺序和清单 SHA-256 与当前证据一致；
9. 查询服务不可用时 API 自动回退 BM25，视频检索不影响手册答案。

完整机器验收命令：

```bash
.venv/bin/python validate_video_analysis.py
```

## 当前边界

当前 `video_scene` 已融合 ASR、OCR 与 VLM 描述，25 个场景均有非空检索文本。检索已支持 BM25、Qwen3 文本向量和二者的加权 RRF，但 dense 索引仍来自场景文本，不等同于原始视频的视觉向量召回。下一阶段需要增加直接视觉/视频 embedding 和可选 rerank，并用来源隔离的三人人工标注查询集评估。固定配置与当前工程结果见 `docs/VIDEO_DENSE_RETRIEVAL_BASELINE_2026-07-20.md`。
