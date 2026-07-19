# API 接口说明

## 基本信息

- 服务入口：`api_server.py`
- 启动脚本：`./run_api.sh`
- 健康检查：`GET /health`
- 对话接口：`POST /chat`
- 默认端口：`8000`
- 认证：`Authorization: Bearer $KAFU_API_TOKEN`

## 启动

```bash
pip install -r requirements.txt
./run_api.sh
```

如需自定义监听地址：

```bash
HOST=127.0.0.1 PORT=8000 ./run_api.sh
```

## GET /health

```bash
curl http://127.0.0.1:8000/health
```

返回示例：

```json
{
  "status": "ok",
  "engine_ready": true,
  "timeout_s": 50.0,
  "multimodal_timeout_s": 60.0,
  "auth_configured": true,
  "classifier_provider": "deepseek_binary_vote",
  "classifier_configured": true,
  "classifier_model": "deepseek-v4-flash"
}
```

## POST /chat

### 请求头

```text
Authorization: Bearer <your-token>
Content-Type: application/json
```

### 请求体

```json
{
  "question": "椅子的扶手使用一段时间后为什么会松动？",
  "images": [],
  "session_id": "demo",
  "stream": false
}
```

字段说明：

| 字段 | 类型 | 必选 | 说明 |
| --- | --- | --- | --- |
| `question` | string | 是 | 用户问题，不能为空。 |
| `images` | array[string] | 否 | Base64 data URL 图片，格式如 `data:image/png;base64,...`，最多 3 张。 |
| `session_id` | string | 否 | 会话 ID；不传时服务端自动生成。 |
| `stream` | boolean | 否 | 兼容字段，当前统一同步返回完整答案。 |

### 调用示例

```bash
curl -sS -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer $KAFU_API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "椅子的扶手使用一段时间后为什么会松动？",
    "session_id": "demo"
  }'
```

### 成功响应

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "answer": "...",
    "session_id": "demo",
    "timestamp": 1780000000,
    "videos": [
      {
        "scene_id": "camera-001-scene-0001",
        "record_id": "camera-001",
        "product_class": "Camera",
        "start_seconds": 0.0,
        "end_seconds": 25.4,
        "clip_url": "/video-media/processed/camera-001/clips/camera-001-scene-0001.mp4",
        "thumbnail_url": "/video-media/keyframes/camera-001/frame_000000.jpg",
        "score": 6.2,
        "evidence_text": "ASR: ..."
      }
    ]
  }
}
```

其中 `data.answer` 与离线 CSV 提交 `ret` 字段同源：

- 客服题：纯文本客服回答。
- 技术题：正文 + `<PIC>` 锚点 + 末尾图片数组字符串。
- `videos`：技术题命中的 0–3 个视频场景；客服题或无匹配时为空数组。

`clip_url` 与 `thumbnail_url` 需要携带相同的 Bearer Token 请求。媒体端点只允许读取项目生成的 MP4 片段和 JPG 关键帧：

```bash
curl -H "Authorization: Bearer $KAFU_API_TOKEN" \
  http://127.0.0.1:8000/video-media/processed/camera-001/clips/camera-001-scene-0001.mp4 \
  -o scene.mp4
```

离线验证视频排名、响应序列化和媒体目录边界：

```bash
python validate_video_retrieval.py
```

## 错误响应

常见错误：

| HTTP 状态码 | 场景 |
| ---: | --- |
| 401 | 缺少 Bearer Token 或 Token 错误。 |
| 422 | 请求字段校验失败，如问题为空、图片格式错误、图片过大。 |
| 500 | Agent 或上游模型内部错误。 |
| 504 | Agent 超时。 |

## 配置覆盖

默认配置写在 `config_runtime.py`。如需覆盖，可在启动前设置同名环境变量，例如：

```bash
SILICONFLOW_BASE_URL="https://your-openai-compatible-endpoint/v1" \
SILICONFLOW_API_KEY="sk-..." \
SILICONFLOW_MODEL="gpt-5.5" \
./run_api.sh
```

默认 embedding / rerank 使用硅基流动远程服务，无需本地启动额外服务。
