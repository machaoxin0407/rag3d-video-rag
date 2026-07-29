# P1 三模态产品闭环完成与验收报告

日期：2026-07-29  
验证代码提交：`9a1a6da`  
分支：`agent/environment-baseline`

## 1. 结论

P1 工程开发和服务器闭环验收已完成，可以进入 P2 正式量化评测。

当前产品已经具备：

- 严格生产配置的 BM25 + Dense + Visual Tri-Hybrid 视频检索；
- 视频证据在答案生成前注入，与 Agent 手册证据联合回答；
- 结构化且经过答案支持检查的手册/视频引用；
- 可鉴权访问的真实手册图片、视频缩略图和裁剪片段；
- 用户视频异步上传、真实媒体校验、均匀抽帧、标准视频与手册步骤先检索后诊断；
- 低置信度、高风险和模型故障的确定性安全降级；
- 文本、图片、视频统一 Web 演示页；
- API、Worker、Dense、Visual 四进程隔离；
- 主机与 Compose 部署配置、TLS 反向代理模板、健康检查和资源释放命令。

用户视频诊断功能仍按“实验性功能”标记。其 Macro-F1、性能和泛化能力必须在
P2 完成后，才能写成论文中已经验证的主要贡献。

## 2. 独立验收问题及修正

主实现完成后，独立子 Agent 首轮给出“有条件不通过”。对应问题均已修正：

| 独立审计问题 | 修正结果 |
| --- | --- |
| 诊断后检索标准视频，且没有手册对齐 | 改为先检索标准视频和手册章节，再把标准证据与用户关键帧共同送入 VLM |
| 低置信度与高风险没有确定性策略 | `<0.55` 自动改为 `insufficient_evidence`；`unsafe_action` 使用停止操作模板 |
| 无产品查询可能误报严格 Tri-Hybrid | 严格模式先验证 Dense/Visual 实际可用，再执行产品和意图拒绝 |
| 固定 Top-K 返回无关视频 | 增加意图门、负面规则及与产品别名解耦的内容 BM25 最低相关性阈值 |
| 所有召回证据都被标为支持答案 | 手册按句子词项重合校验；视频仅在答案包含对应 `[VID:scene_id]` 时形成 citation |
| 手册图片 URL 没有真实扩展名 | 图片 ID 映射为真实 JPG/PNG 文件，并读取正式图片 caption |
| 状态文件跨进程不安全 | 增加跨进程排他锁、陈旧锁恢复、原子替换写入、Worker 租约和超时恢复 |
| 上传中断遗留临时任务 | 增加仅限 uploading 状态的内部 discard 路径和回归测试 |
| 可删除运行中的任务 | 活动任务删除返回 HTTP 409；仅 completed/failed 可删除 |
| 供应商错误和内部路径可能返回页面 | 后台错误分类化，HTTP 500 返回固定脱敏信息 |
| Compose 无法访问宿主机 loopback 模型 | Linux server override 改用 host network；API 仍只绑定 127.0.0.1 |
| 裁剪片段错误跳到原视频 start_seconds | 裁剪片段从 0 秒播放，界面单独显示原视频时间边界 |
| 手册图片不可放大 | 增加键盘可访问的 modal/lightbox |
| smoke 没有强断言 | 增加 health、exact mode、回答、引用、媒体实体和视频任务终态断言 |

## 3. 本地自动验收

命令：

```bash
python validate_p1_product.py
python -m ruff check api_server.py video_job_worker.py video_rag/diagnosis.py \
  video_rag/retrieval.py deploy/server_p1_smoke.py tests/test_p1_product.py
```

结果：

- 10 项 P1 单元测试通过；
- Python 编译通过；
- P1 修改文件 Ruff 检查通过；
- `git diff --check` 通过；
- 无关查询 `Tell me a joke about an air fryer` 和退款/保修电话查询返回空视频；
- 带操作词但不存在的传真模块、蓝光播放问题也被内容相关性阈值拒绝；
- 中文手册改写能够生成句子级支持引用；
- 上传失败可清除 uploading 任务，陈旧跨进程锁可自动恢复；
- 严格 Tri-Hybrid 服务不可用时抛出错误，不静默回退；
- 活动任务禁止删除；
- 无 `[VID:...]` 的答案不会生成对应视频 citation；
- `Manual08_0` 正确映射到真实 `Manual08_0.jpg`。

## 4. 服务器验收

服务器目录：`~/rag3d-video`

### 4.1 部署配置

以下检查通过：

```bash
docker compose -f compose.yaml -f compose.server.yaml config --quiet
python validate_p1_product.py
```

服务器主机运行时使用：

- GPU0：Dense 文本视频检索服务；
- GPU1：Visual 视频检索服务；
- API：`127.0.0.1:8000`；
- 独立视频 Worker：磁盘队列与原子任务状态；
- 生产 profile：`VIDEO_RUNTIME_PROFILE=production`；
- 精确模式：`VIDEO_RETRIEVAL_MODE=tri_hybrid`、
  `VIDEO_REQUIRE_EXACT_MODE=1`。

### 4.2 冻结 100 问题在线检索

执行：

```bash
python validate_p1_online_retrieval.py
```

结果：

```json
{
  "status": "passed",
  "queries": 100,
  "strict_tri_hybrid_queries": 100,
  "failures": []
}
```

机器可读报告：
`validation_outputs/p1_online_100_report.json`

SHA-256：
`182c8f037949ede87434f9da64ee92a408f03377754a0a14c18182fc90ea098b`

### 4.3 认证端到端 smoke

`deploy/server_p1_smoke.py` 最终结果：

```json
{
  "status": "passed",
  "health": "ok",
  "exact_ready": true,
  "chat": {
    "route": "tech",
    "requested_mode": "tri_hybrid",
    "effective_mode": "tri_hybrid",
    "videos": 3,
    "citations": 3,
    "answer_chars": 614,
    "authenticated_media": 3
  },
  "video_job": {
    "status": "completed",
    "label": "insufficient_evidence",
    "error": null
  }
}
```

黑屏合成视频被安全判为 `insufficient_evidence`，没有生成操作正确性的虚假结论。
完成后测试任务通过 DELETE 接口删除。

### 4.4 资源释放

最终执行：

```bash
./p1_stack.sh release
```

API、Worker、Dense 和 Visual 均由本项目 PID 文件停止；两张 GPU 不再有本项目
计算进程。数据集、索引、标注、报告和其他工程进程均未清理。

## 5. 配置与访问

服务器令牌已与其他工程分离并轮换。用户本机访问令牌文件：

`C:\Users\MAXS\Desktop\RAG3D_P1_ACCESS_TOKEN.txt`

该文件不得提交 Git 或发送到论文附件。演示服务默认不常驻；需要使用时：

```bash
cd ~/rag3d-video
./p1_stack.sh start
```

本机建立 SSH 隧道：

```bash
ssh -L 8000:127.0.0.1:8000 newpulse-server
```

浏览器打开 `http://127.0.0.1:8000/demo`。

使用结束：

```bash
./p1_stack.sh release
```

## 6. 明确保留给 P2 的工作

以下不是 P1 工程阻塞项，但没有完成前不能扩大论文主张：

1. 诊断受控偏差小集和 Macro-F1；
2. 100 问题端到端答案正确率、手册/视频证据支持率和拒答正确率；
3. 100 问题图片章节一致性与媒体有效率批量报告；
4. 六类产品的浏览器人工演示；
5. 60 秒视频耗时和 GPU 显存统计；
6. 并发 2/4/8 的 P50/P95/P99；
7. Dense、Visual、VLM 和主答案模型故障注入；
8. 24 小时稳定性；
9. 时间定位、消融、泛化和论文端到端质量实验。

手册 Dense/Rerank 的线上凭据未与冻结手册索引模型同源，因此当前 P1 主机部署
显式使用手册 BM25 召回，避免把不同 embedding 空间错误混用。视频检索仍为真实
Tri-Hybrid。P2 若恢复同源手册 embedding/rerank，必须重新做端到端对照评测。
