# 视频稠密与混合检索基线（2026-07-20）

## 结论

视频检索已从纯 BM25 扩展为三种可切换模式：

- `bm25`：原有词法检索；
- `dense`：Qwen3 文本向量余弦相似度；
- `hybrid`：BM25 与 dense 的加权 Reciprocal Rank Fusion（RRF）。

当前 dense 索引编码的是每个视频场景已经融合的 ASR、OCR、Qwen3-VL 描述和产品别名。因此，这是“带视觉描述的场景文本稠密检索”。项目随后已增加 `Qwen3-VL-Embedding-2B` 直接视频基线，配置与实测见 `docs/VIDEO_VISUAL_RETRIEVAL_BASELINE_2026-07-20.md`。

## 固定配置

| 项目 | 当前值 |
|---|---|
| 文本向量模型 | `Qwen/Qwen3-Embedding-0.6B` |
| 模型修订号 | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| 向量维度 | 1024 |
| 场景数量 | 25 |
| 向量归一化 | L2 |
| 索引文件 | `data_video/indexes/video_dense_qwen3_embedding_0_6b.npz`（Git 忽略） |
| 索引大小 | 63,613 bytes |
| 查询提示 | 产品支持问题 → 相关对象、部件、状态或操作场景 |
| 混合方法 | `0.45/(60+BM25 rank) + 0.55/(60+dense rank)` |
| 单来源上限 | 每个 `record_id` 最多返回 2 个场景 |
| 默认模式 | `hybrid`；dense 不可用时自动回退 `bm25` |

索引保存场景顺序、模型与修订号、维度、清单 SHA-256 和生成时间。加载时会重新计算证据清单与来源清单 SHA-256；清单内容改变、场景顺序改变、索引损坏或查询服务异常时，主 API 不使用该索引并回退到 BM25。

模型选择依据：

- Qwen3-Embedding-0.6B 支持 100 多种语言、最长 32K token、最高 1024 维，并支持 instruction-aware query 和 Matryoshka 维度裁剪：
  <https://huggingface.co/Qwen/Qwen3-Embedding-0.6B>
- Qwen3-VL-Embedding 支持文字、图片、视频和混合输入；其 2B 版本作为后续直接跨模态消融候选：
  <https://github.com/QwenLM/Qwen3-VL-Embedding>

## 隔离与部署

嵌入组件位于独立 `.venv-embedding`，不会覆盖 ASR、OCR、VLM 或主 API 环境：

```bash
cd ~/rag3d-video
./setup_video_embedding_environment.sh

HF_ENDPOINT=https://hf-mirror.com \
HF_HUB_DISABLE_XET=1 \
CUDA_VISIBLE_DEVICES=0 \
.venv-embedding/bin/python build_video_dense_index.py --device cuda:0
```

查询模型由仅监听 `127.0.0.1` 的独立服务承载：

```bash
./video_embedding_service.sh start
./video_embedding_service.sh status
./video_embedding_service.sh stop
```

主 API 的 `.env` 使用：

```dotenv
VIDEO_RETRIEVAL_MODE=hybrid
VIDEO_DENSE_ENDPOINT=http://127.0.0.1:8091
VIDEO_DENSE_TIMEOUT_S=1.5
```

产品运行时可以让嵌入服务常驻；离线实验结束必须执行 `stop`。本次停止后 GPU 0/1 显存分别回到 41 MiB/15 MiB。

## 服务器验收结果

### 临时种子集

`evaluate_video_retrieval.py` 使用 9 个中英文场景问题检查排序。这些标签由开发阶段预置，只是回归集，不是人工金标准，不得直接作为论文主结果。

| 模式 | Hit@1 | Hit@3 | MRR@3 |
|---|---:|---:|---:|
| BM25 | 0.778 | 0.889 | 0.833 |
| Dense | 0.778 | 1.000 | 0.870 |
| Hybrid | **0.889** | **1.000** | **0.944** |

混合检索修复了“完成的浓缩咖啡放在机器旁”这一 BM25 Top-3 漏检。关于“两台相机放在蓝色桌上”的问题仍排第 2，后续人工标注集会判断这是否属于真实错误。

### 产品链路

下列检查全部通过：

- 6 个产品类别查询均返回同类视频；
- 技术问题 `/chat` 响应携带视频证据；
- 服务问题不返回视频；
- 片段和缩略图路径可解析；
- HTTP 视频片段返回 `video/*`；
- `../.env` 等目录穿越被拒绝；
- dense 服务停止后，请求立即回退 BM25，主 API 不报错。

### 延迟与资源

在 RTX 4090、单查询、2 次 warm-up、10 次计时条件下：

- hybrid 中位延迟：33.027 ms；
- hybrid P95：34.236 ms；
- 查询服务常驻显存：约 1,679 MiB；
- 服务停止后显存：41 MiB；
- 模型缓存：1.2 GiB；
- 独立环境：6.8 GiB。

这些是服务器单进程工程测量，不是论文吞吐基准。正式实验需要固定并发、预热、查询长度、重复次数和置信区间。

## 三人标注与正式评估

标注工作簿包含：

- 25 个 VLM 场景的 A/B 独立复核与 C 仲裁；
- 100 个检索问题槽位；
- A/B 的相关性等级、时间边界标签与来源泄漏检查；
- C 的最终相关性与最终时间范围；
- 自动进度与分歧统计。

正式论文结果必须在 100 个问题冻结、三人完成后计算。至少报告：

- Recall@1/3/5、MRR@10、nDCG@10；
- 时间 IoU、mAP@0.3/0.5；
- 按产品、语言、问题类型分层结果；
- BM25、dense text、hybrid、直接视觉/视频向量、是否使用 VLM 描述的消融；
- bootstrap 95% 置信区间和配对显著性检验；
- 来源隔离测试集结果，不能只使用与训练/开发同来源的视频。

## 下一步

1. 三位标注员先独立完成 25 个场景复核，再由 C 仲裁。
2. 用统一模板撰写 100 个问题，先冻结问题与来源切分再调权重。
3. 增加 `Qwen3-VL-Embedding-2B` 的帧/视频直接向量基线。
4. 只在开发集选择 RRF 权重和候选数；测试集不参与调参。
5. 将正式标注导出为机器可读 JSONL，生成可复现评测表与论文图。
