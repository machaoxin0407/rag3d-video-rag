# P1 三模态产品部署与操作手册

更新日期：2026-07-29

## 1. 本阶段交付

P1 在保留原 `/chat` 兼容接口的基础上新增：

- `/v2/chat`：先执行视频 Tri-Hybrid 检索，再与 Agent 的手册检索结果联合生成答案；
- 结构化 `citations`、`manual_images`、`videos` 与 `retrieval` 状态；
- `/v2/video-jobs` 异步视频诊断任务；
- `/demo` 文本、图片和视频统一演示页；
- API、视频 Worker、Dense 与 Visual 四个独立进程；
- Docker/Compose 骨架、主机启动脚本、健康检查和资源释放命令。

生产配置设为 `VIDEO_RETRIEVAL_MODE=tri_hybrid` 和
`VIDEO_REQUIRE_EXACT_MODE=1`。Dense 或 Visual 不可用时，技术问题返回
HTTP 503，不再静默退化为 BM25。

## 2. 服务器前置条件

- Ubuntu 服务器、NVIDIA 驱动和两张 RTX 4090；
- 项目位于 `~/rag3d-video`；
- `.venv`、`.venv-embedding`、`.venv-visual-embedding` 已按现有脚本建立；
- `ffmpeg`、`ffprobe` 和 `curl` 可用；
- `.env` 只保存在服务器，至少配置 `KAFU_API_TOKEN`、主回答模型、
  embedding 与 rerank 的密钥；
- GPU0 固定运行 Dense 文本模型，GPU1 固定运行 Visual 模型。

用户视频视觉诊断需要另外配置：

```bash
USER_VIDEO_VLM_BASE_URL=https://your-openai-compatible-endpoint/v1
USER_VIDEO_VLM_API_KEY=...
USER_VIDEO_VLM_MODEL=your-vision-model
```

未配置时仍会完成文件和关键帧检查，但诊断必须返回
`insufficient_evidence`，不会生成未经视觉检查的结论。

## 3. 主机方式启动

```bash
cd ~/rag3d-video
chmod +x p1_stack.sh video_embedding_service.sh video_visual_embedding_service.sh
./p1_stack.sh start
./p1_stack.sh status
```

服务只绑定 `127.0.0.1:8000`。从个人电脑安全访问可使用 SSH 隧道：

```bash
ssh -L 8000:127.0.0.1:8000 newpulse-server
```

随后打开 `http://127.0.0.1:8000/demo`。需要公网访问时，使用
`deploy/nginx.p1.conf.example` 配置已申请证书和域名的 Nginx TLS 反向代理；
不要直接把 Uvicorn 暴露到公网。

停止并释放两张 GPU：

```bash
./p1_stack.sh release
```

该命令只停止本项目 PID 文件登记的 API、Worker、Dense 和 Visual 进程，
不清理数据集、索引或其他工程文件。

## 4. Compose 方式

Dense 和 Visual 模型继续使用已有、相互隔离的 GPU 虚拟环境在主机运行。
API 与异步 Worker可用 Compose 隔离：

```bash
./video_embedding_service.sh start
./video_visual_embedding_service.sh start
docker compose -f compose.yaml -f compose.server.yaml up -d --build
docker compose ps
```

停止：

```bash
docker compose -f compose.yaml -f compose.server.yaml down
./video_visual_embedding_service.sh stop
./video_embedding_service.sh stop
```

## 5. API 操作

联合回答：

```bash
curl -sS http://127.0.0.1:8000/v2/chat \
  -H "Authorization: Bearer $KAFU_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"空气炸锅第一次使用前需要做什么？","images":[]}'
```

返回的 `retrieval.requested_mode` 和 `effective_mode` 应同时为
`tri_hybrid`。`videos[].start_seconds/end_seconds` 是播放器定位边界。

创建视频任务：

```bash
curl -sS http://127.0.0.1:8000/v2/video-jobs \
  -H "Authorization: Bearer $KAFU_API_TOKEN" \
  -F "video=@sample.mp4" \
  -F "product_class=Air Fryer" \
  -F "question=这一步操作是否正确？"
```

用返回的 `job_id` 查询状态和结果：

```bash
curl -sS -H "Authorization: Bearer $KAFU_API_TOKEN" \
  http://127.0.0.1:8000/v2/video-jobs/JOB_ID
curl -sS -H "Authorization: Bearer $KAFU_API_TOKEN" \
  http://127.0.0.1:8000/v2/video-jobs/JOB_ID/result
```

明确删除某个用户视频任务及其临时副本：

```bash
curl -X DELETE -H "Authorization: Bearer $KAFU_API_TOKEN" \
  http://127.0.0.1:8000/v2/video-jobs/JOB_ID
```

## 6. 安全边界

- 上传只接受 MP4、MOV、WebM、M4V，最大 200 MB、60 秒、4K 像素量；
- 文件扩展名和 MIME 通过后仍由 `ffprobe` 验证真实视频流；
- 服务端路径由随机 `job_id` 产生，上传文件名不参与路径构造；
- 原始数据集视频不可通过媒体 API 访问；
- 手册图片和生成视频片段均需 Bearer 鉴权；
- 日志只记录问题摘要、计数、状态和任务 ID，不记录 Base64 或视频内容；
- 用户视频不自动混入训练集或论文数据集。

## 7. 验收与故障定位

静态和单元验收：

```bash
python validate_p1_product.py
```

在线健康检查：

```bash
curl -sS http://127.0.0.1:8000/health | python -m json.tool
```

生产可用条件：

- `status=ok`；
- `video_retrieval.exact_ready=true`；
- Dense/Visual 两个服务 `ready=true`；
- `/v2/chat` 技术问题的 `effective_mode=tri_hybrid`；
- 视频任务能从 `queued` 进入 `completed` 或有明确 `failed` 原因。

诊断 Macro-F1、60 秒视频耗时和 100 问题端到端批量评测属于下一阶段 P2 的
正式量化验收。在这些指标完成前，用户视频诊断在论文和产品中必须标记为
“实验性功能”，不能写成已验证的主要贡献。
