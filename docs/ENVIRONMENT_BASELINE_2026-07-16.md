# 研发与服务器环境基线

> 记录日期：2026-07-16
>
> 代码基线提交：`72abc784c3c979c7653f74c8bef14e2588c90443`
>
> 私有仓库：`machaoxin0407/rag3d-video-rag`

## 本地代码基线

- Python：3.11.9；
- 静态交付检查：通过，0 warning；
- 检索索引：成功加载；
- Retrieval chunks：6,570；
- Parent sections：1,943；
- Products：39；
- FAISS vectors：6,570；
- GitHub 暂存密钥模式扫描：未发现匹配；
- `run_api.sh` / `smoke_test.sh`：Git 模式 `100755`。

## GitHub

- 仓库可见性：Private；
- 默认分支：`main`；
- 首次提交：`72abc78`；
- 服务器访问：项目专用只读 Deploy Key；
- 服务器不保存 GitHub 个人 Token；
- `.env`、视频原文件、模型权重、日志和缓存均被 Git 忽略。

## 服务器

- SSH 别名：`newpulse-server`；
- 操作系统：Ubuntu 22.04.5 LTS；
- 账号：`mcx2025`，无 sudo，具备 Docker 组权限；
- 项目目录：`~/rag3d-video`；
- Python：3.10.12；
- Python venv：可用；
- Docker Engine：29.1.3；
- Docker Compose：2.40.3；
- GPU：2 × NVIDIA GeForce RTX 4090 24GB；
- GPU 驱动：580.159.03；
- 检查时 GPU：两卡空闲，无计算进程；
- 内存：251GB，总可用约236GB；
- 根盘：3.5TB，剩余约327GB，使用率91%；
- 独立数据盘：无；
- FFmpeg/ffprobe：未安装；
- 系统 CUDA Toolkit/nvcc：未安装；
- 系统 Python 中未安装 PyTorch、FAISS、FastAPI 等项目依赖。

## 隔离边界

- 不修改 `~/newpulse-mail`；
- 不访问或覆盖 `~/newpulse-mail/.env`；
- 不复用其数据库、Redis、MinIO、端口或 Compose project；
- 本项目不启动常驻服务，直到端口、资源和安全配置另行冻结；
- GPU 任务结束后必须检查并释放进程与显存；
- 未经额外授权不执行 Docker 镜像、容器、卷或系统磁盘清理。

## 当前阻塞与后续动作

1. 服务商侧旧 API Key 与旧 Bearer Token 仍需项目负责人吊销/轮换；
2. 服务器无 sudo，FFmpeg 需采用用户级静态包、Conda/Micromamba 或容器方案；
3. 剩余磁盘不足以直接保存完整25–40小时视频、所有关键帧和多套模型，第一周试验数据限制在30GB以内；
4. 先建立隔离 Python 环境并复现静态检查/索引加载；
5. 再验证小规模 FFmpeg、ASR、OCR 和视频模型，不进行大规模下载或训练。
