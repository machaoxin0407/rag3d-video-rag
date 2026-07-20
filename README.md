# KBrag V6 多模态客服智能体提交代码

这是 DataFountain「具有多模态能力的客服智能体设计」赛道的 V6 初赛提交代码包。目录已按“评审可直接启动验证”的方式整理：默认配置、检索索引、手册数据和图片资源已随代码放入本目录，通常不需要额外启动本地 embedding / rerank 服务。

## 目录说明

- `api_server.py`：RESTful `/chat` 在线接口入口。
- `agent.py`：客服 / 技术双轨 Agent 主流程。
- `retrieval_engine.py`：BM25 + dense + RRF + rerank 混合检索。
- `product_router.py`：产品路由。
- `llm_router.py`：主回答模型路由。
- `submission_utils.py`：`[[PIC]]` / `<PIC>` 图片锚点和提交格式处理。
- `skills/search_manual.md`：`search_manual` 工具使用 SOP，固定注入技术 prompt。
- `data/`：已构建好的检索索引和运行元数据。
- `手册_v4/`：V6 整理后的 Markdown 手册知识库。
- `手册/插图/`：手册插图资源。
- `config_runtime.py`：初赛提交版默认 endpoint、token、timeout 与模型服务配置。
- `.env.example`：私有部署时的环境变量覆盖模板。
- `run_api.sh`：一键启动 API。
- `smoke_test.sh`：一键健康检查和 `/chat` 示例调用。
- `validate_delivery.py`：交付包静态自检脚本。
- `validate_performance.py`：验证报告数据表生成脚本。
- `video_rag/`：授权视频预处理、ASR/OCR/VLM、证据融合和本地视频检索。
- `run_video_analysis_stage.sh`：镜头、ASR、OCR、VLM 与证据构建的服务器统一入口。
- `validate_video_analysis.py` / `validate_video_retrieval.py`：视频产物完整性与 API 合约验收。
- `validation_outputs/`：验证报告 CSV/JSON/Markdown 产物。
- `delivery_docs/`：初赛 Markdown 交付材料，覆盖 API 接口、源码运行、技术方案和验证报告。

## 快速启动

建议使用 Python 3.10+ / 3.11。

```bash
pip install -r requirements.txt
./run_api.sh
```

服务默认监听：

```text
http://0.0.0.0:8000
```

另开一个终端执行 smoke：

```bash
./smoke_test.sh
```

压包或提交前建议执行静态自检：

```bash
python validate_delivery.py
```

生成验证报告数据表：

```bash
python validate_performance.py
```

若 API 服务已启动，可追加在线对话连贯性验证：

```bash
python validate_performance.py --api-base-url http://127.0.0.1:8000
```

预期 `/health` 返回 `status=ok`，`/chat` 返回如下结构：

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "answer": "...",
    "session_id": "demo",
    "timestamp": 1780000000,
    "videos": []
  }
}
```

## API 调用

### Health

```bash
curl http://127.0.0.1:8000/health
```

### Chat

Bearer Token 必须通过 `KAFU_API_TOKEN` 环境变量或未纳入 Git 的 `.env` 配置：

```text
replace-with-random-token
```

示例：

```bash
curl -sS -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $KAFU_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "椅子的扶手使用一段时间后为什么会松动？",
    "session_id": "demo"
  }'
```

请求字段：

| 字段 | 必选 | 说明 |
| --- | --- | --- |
| `question` | 是 | 用户问题。 |
| `images` | 否 | Base64 data URL 图片数组，最多 3 张；接口校验并随本轮消息传入模型。 |
| `session_id` | 否 | 会话 ID，用于短历史拼接、日志追踪和连续追问演示。 |
| `stream` | 否 | 兼容字段，当前同步返回完整结果。 |

技术问题会在 `data.videos` 中附加最多 3 个相关视频场景，包含起止时间、鉴权 MP4 URL、关键帧 URL 和证据文本。客服问题或没有视频匹配时返回空数组。详细字段与媒体下载方式见 `API.md`。

## 初赛交付 Markdown 材料

本代码包已补充初赛要求的 Markdown 交付材料：

```text
delivery_docs/
├── 00_提交材料总览.md
├── 01_API接口说明.md
├── 02_源码运行说明.md
├── 03_技术方案说明.md
└── 04_验证报告.md
```

这组文档对应初赛要求的 4 类核心材料：智能体 API 接口、源码运行说明、技术文档和验证报告。PDF 转换由后续提交流程处理，本代码包只维护 Markdown 源稿。

## 默认配置

交付版默认配置集中在：

```text
config_runtime.py
```

其中包含：

- `/chat` Bearer Token。
- DeepSeek V4 Flash 三路二分类路由器。
- GPT-5.5 OpenAI-compatible 主回答模型。
- 硅基流动远程 embedding / rerank。
- 超时、并发和 token 参数。

`api_server.py` / `llm_router.py` 启动时会调用 `apply_default_env()`，只对尚未设置的环境变量填默认值。因此如果评审环境希望替换 key 或 endpoint，可以直接：

1. 修改 `config_runtime.py`；或
2. 启动前设置同名环境变量覆盖。

## 复现离线提交

如需按题目 CSV 离线生成提交，可使用：

```bash
python generate_submission_v5.py --ids 246,303,401 --workers 3 --out-prefix v6_smoke --reset
```

全量跑批需要上游模型 endpoint 可用，且耗时较长。在线评审建议优先使用 `/chat`。

## 注意事项

- 当前目录是初赛交付启动版，包含默认运行配置；如需公开发布，请先完成脱敏和配置替换。
- 默认检索走硅基流动远程 embedding / rerank，不需要本地启动 `embedding_server.py` 或 `rerank_server.py`。
- 当前 ReAct 工具只暴露 `search_manual`；没有恢复旧的 `manual_reader/use_skill/list/read` 工具链。
- `data/index/` 已包含 FAISS 和 BM25 元数据，正常启动无需重建索引。
