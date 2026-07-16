# 第一周服务器执行记录（2026-07-16）

## 已完成

- 建立独立私有 GitHub 仓库与脱敏 `main` 基线；
- 为服务器配置项目专用、只读 Deploy Key；
- 部署代码至 `~/rag3d-video`，当前使用 `agent/environment-baseline` 分支；
- 建立隔离 `.venv`，安装现有 RAG 依赖；
- 安装用户态 FFmpeg，不修改系统包；
- 建立 `data_video/` 的 manifest、annotation、raw、processed、keyframes、transcripts、indexes、splits 目录；
- 固化 `server_smoke_check.py`，可重复检查检索、视频工具和 CUDA；
- 通过现有索引加载、合成视频、抽帧和双卡 CUDA 烟测；
- 创建草稿 PR #1，保留审查与回退入口。

## 尚未完成

- 供应商控制台旧密钥吊销与新密钥注入；
- 8 类目标产品的视频来源与许可审计；
- 三人试标数据与一致性统计；
- 真实视频上的 ASR、OCR、视频编码器和 VLM 对比；
- 在线问答 smoke（缺少轮换后的密钥）；
- 常驻 API 部署（端口、鉴权和资源窗口尚未冻结）。

## 下一执行顺序

1. 负责人完成旧凭据吊销，按 `.env.example` 生成服务器 `.env`；
2. 三人各自收集同一批公开视频候选，只登记 URL、许可、产品、语言和时间段；
3. 冻结 manifest 与 annotation schema，再开始 8–12 个样本的三人试标；
4. 协调一个两张 GPU 均可用的 2 小时窗口；
5. 在不超过 30 分钟真实视频上跑 ASR、OCR、视频编码器和 VLM 候选；
6. 根据质量、速度、显存和许可证确定第二周模型栈。

## 服务器复现命令

```bash
ssh newpulse-server
cd ~/rag3d-video
git status --short --branch
.venv/bin/python validate_delivery.py
.venv/bin/python server_smoke_check.py --create-video-sample
.venv/bin/python server_smoke_check.py --cuda
nvidia-smi --query-compute-apps=pid,process_name,gpu_uuid,used_memory --format=csv,noheader
```

GPU 烟测命令结束后必须执行最后一条命令，确认本项目 Python 进程不在列表中。
