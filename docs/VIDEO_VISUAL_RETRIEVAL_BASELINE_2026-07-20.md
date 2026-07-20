# 直接视频向量检索基线（2026-07-20）

## 结论

项目已经增加真正读取场景 MP4 画面的跨模态检索基线。该基线不使用 ASR、OCR 或 VLM caption 作为文档输入，而是用 `Qwen3-VL-Embedding-2B` 把视频场景映射到 2048 维向量，再用同一模型编码中英文文本问题。

现有检索模式扩展为：

- `bm25`：场景融合文本的词法检索；
- `dense`：Qwen3-Embedding-0.6B 场景文本向量；
- `visual`：Qwen3-VL-Embedding-2B 直接视频向量；
- `hybrid`：BM25 + text dense；
- `tri_hybrid`：BM25 + text dense + direct video。

默认产品配置仍保持 `hybrid`，不因 9 个开发问题上的结果立即切换。待 100 个问题完成三人标注并冻结开发/测试切分后，再决定默认模式和融合权重。

## 官方依据与版本

官方模型卡说明该模型为 Apache-2.0，支持文字、图片、视频和混合输入，参数量 2B，最大输出维度 2048，并建议为具体任务编写英文 instruction：

- <https://huggingface.co/Qwen/Qwen3-VL-Embedding-2B>
- <https://github.com/QwenLM/Qwen3-VL-Embedding>

固定版本：

| 项目 | 固定值 |
|---|---|
| 模型 | `Qwen/Qwen3-VL-Embedding-2B` |
| 模型修订号 | `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda` |
| 模型内实现脚本 Git blob | `36d45865735be96a1278a21c132ff640e2ae68ca` |
| Python | 3.11.15 |
| PyTorch | 2.8.0+cu128 |
| Transformers | 4.57.3 |
| qwen-vl-utils | 0.0.14 |
| 数据类型 | BF16 |
| Attention | PyTorch SDPA |
| 许可证 | Apache-2.0 |

## 视频索引配置

| 项目 | 值 |
|---|---:|
| 场景数 | 25 |
| 视频采样 | 1 fps |
| 每场景最大帧数 | 8 |
| 总像素上限 | 4,194,304 |
| 向量维度 | 2048 |
| L2 归一化 | 是 |
| 构建时间 | 10.103 秒 |
| 索引大小 | 115,179 bytes |
| 单帧回退 | `espresso-001-scene-0001` |

`espresso-001-scene-0001` 的 MP4 只有一个可解码视频帧，而官方视频处理器至少需要两帧，因此该场景使用其审计缩略图生成图像向量。构建程序会先用 OpenCV 检查可解码帧数，并把所有回退场景写入索引 metadata。其余 24 个场景均直接读取 MP4。

索引保存：

- evidence 与 inventory 的 SHA-256；
- 模型和实现修订号；
- 视频采样参数；
- 场景顺序；
- 单帧回退列表；
- 完成状态、构建时间和向量维度。

构建过程中每完成一个场景写入 `.partial.npz`；中断后只有在清单散列、模型版本和采样参数全部一致时才允许续跑。

## 环境与命令

视觉模型使用独立环境，不改动主 API、ASR、OCR、VLM 或 text-dense 环境：

```bash
cd ~/rag3d-video
HF_ENDPOINT=https://hf-mirror.com \
HF_HUB_DISABLE_XET=1 \
CUDA_VISIBLE_DEVICES=1 \
./setup_video_visual_embedding_environment.sh
```

构建索引：

```bash
CUDA_VISIBLE_DEVICES=1 \
.venv-visual-embedding/bin/python build_video_visual_index.py \
  --fps 1.0 \
  --max-frames 8 \
  --total-pixels 4194304
```

服务启停：

```bash
VIDEO_VISUAL_CUDA_VISIBLE_DEVICES=1 ./video_visual_embedding_service.sh start
./video_visual_embedding_service.sh status
./video_visual_embedding_service.sh stop
```

服务只监听 `127.0.0.1:8092`。主 API 使用：

```dotenv
VIDEO_VISUAL_DENSE_ENDPOINT=http://127.0.0.1:8092
VIDEO_VISUAL_DENSE_TIMEOUT_S=2.0
```

## 工程验收

### 跨模态 smoke

使用“打印机送纸并输出图像”问题进行 text-to-video 验证：

| 视频 | 相似度 |
|---|---:|
| 打印机场景 | 0.640062 |
| 压力锅负例 | 0.302437 |

三个向量形状均为 2048，BF16 归一化误差小于 0.005。

### 9 问题临时回归集

| 模式 | Hit@1 | Hit@3 | MRR@3 |
|---|---:|---:|---:|
| BM25 | 0.778 | 0.889 | 0.833 |
| Text dense | 0.778 | 1.000 | 0.870 |
| Direct video | **1.000** | **1.000** | **1.000** |
| BM25 + text dense | 0.889 | 1.000 | 0.944 |
| 三路融合 | 0.889 | 1.000 | 0.944 |

直接视频模式在这 9 个问题上最好，但这组问题来自开发阶段，数量很小且没有经过三人独立标注。因此：

- 不能将 `1.000` 写成论文主结果；
- 不能用这 9 个问题调整三路融合权重；
- 不能据此把产品默认模式从 `hybrid` 改为 `visual`。

### 延迟和资源

单查询、2 次预热、10 次计时：

| 模式 | 中位延迟 | P95 |
|---|---:|---:|
| Direct video query | 29.645 ms | 29.975 ms |
| 三路融合 | 68.974 ms | 77.605 ms |

资源：

- 视觉查询服务单独常驻 GPU1：4,473 MiB；
- text-dense 与视觉服务同时常驻 GPU1：约 6,025 MiB；
- 两个服务停止后 GPU1：18 MiB；
- 视觉环境：6.9 GiB；
- 模型缓存：4.0 GiB。

GPU0 在本次实验期间存在另一位用户的训练进程，本项目没有终止、暂停或修改该进程；所有视觉实验固定使用 GPU1。

## 降级行为

`tri_hybrid` 会按可用组件逐级降级：

```text
text dense + visual available -> tri_hybrid
only text dense available     -> hybrid
only visual available         -> visual_hybrid
neither available             -> bm25
```

服务器已实测：

- 停止视觉服务后，`tri_hybrid` 自动变为 `hybrid`；
- 再停止 text-dense 服务后，自动变为 `bm25`；
- API、媒体鉴权和路径穿越防护仍通过；
- 服务停止后 GPU1 显存恢复到 18 MiB。

## 论文下一步

完成三人 100 问题标注后，固定报告：

1. BM25、text dense、direct video、两路融合和三路融合；
2. 是否加入 VLM caption 的消融；
3. 1/4/8/16 帧和不同像素预算的效率—效果曲线；
4. 中英文、对象、部件、状态、动作、时间定位分层结果；
5. Recall@K、MRR、nDCG、时间 IoU/mAP；
6. bootstrap 95% 置信区间与配对显著性检验；
7. 来源隔离的独立测试集，不允许根据测试结果调权重。
