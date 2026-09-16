# 研发与服务器环境基线

> 记录日期：2026-07-16
>
> 脱敏源码基线：`72abc784c3c979c7653f74c8bef14e2588c90443`
>
> 执行分支：`agent/environment-baseline`
>
> 私有仓库：`machaoxin0407/rag3d-video-rag`

## 本地与 GitHub

- 本地 Python：3.11.9；
- 交付检查通过，0 warning；
- 现有检索资产可加载：39 个产品、1,943 个章节、6,570 个 chunks、6,570 个 FAISS vectors；
- 私有仓库默认分支为 `main`；
- 服务器使用项目专用只读 Deploy Key，不保存个人 GitHub Token；
- `.env`、视频原文件、模型权重、日志、缓存和虚拟环境均被 Git 忽略；
- 草稿 PR：`agent/environment-baseline` → `main`。

## 服务器

- SSH 别名：`newpulse-server`；
- 操作系统：Ubuntu 22.04.5 LTS；
- 账户：`mcx2025`，无 sudo，具备 Docker 组权限；
- 项目目录：`~/rag3d-video`；
- Python：3.10.12；
- 系统缺少 `python3-venv/ensurepip`，因此使用用户级 `virtualenv` 创建 `~/rag3d-video/.venv`；
- Docker Engine：29.1.3；Docker Compose：2.40.3；
- GPU：2 × NVIDIA GeForce RTX 4090，每张 24,564 MiB；驱动 580.159.03；
- 项目虚拟环境：PyTorch 2.7.0+cu128，CUDA runtime 12.8；
- 视频工具：用户态 FFmpeg 7.0.2-static；系统级 FFmpeg 和 nvcc 仍未安装；
- 内存：251 GiB，总可用约 236 GiB；
- 根盘：3.5 TiB，基线剩余约 327 GiB，使用率 91%；无独立数据盘；
- 未执行磁盘、Docker 镜像、容器或卷清理。

## 已通过的服务器烟测

1. `validate_delivery.py`：通过，0 warning；
2. 离线加载现有 BM25/FAISS 检索资产：通过；
3. FFmpeg 生成 3 秒 640×360 带音轨合成视频：通过；
4. 从合成视频抽取 1 秒关键帧：通过；
5. PyTorch 可发现两张 4090，并在每张卡完成 1024×1024 矩阵乘法：通过；
6. CUDA 烟测进程退出后，本项目无残留 compute process。

复现命令：

```bash
cd ~/rag3d-video
.venv/bin/pip install -r requirements-video-base.txt
.venv/bin/pip install -r requirements-gpu-cu128.txt
.venv/bin/python validate_delivery.py
.venv/bin/python server_smoke_check.py --create-video-sample
.venv/bin/python server_smoke_check.py --cuda
```

## GPU 资源观察

2026-07-16 CUDA 烟测开始前，两张卡已被同一个非本项目进程占用约 22.3 GiB/卡，PID 为 `826404`。烟测后显存回到相同水平，说明本项目已释放资源。该外部进程未被终止、修改或重启。后续加载 ASR、VLM 或视频编码器前，必须先协调空闲窗口；不得把该外部进程的占用计入本项目峰值。

## 隔离边界与当前阻塞

- 不修改或复用 `~/newpulse-mail` 的配置、容器、数据库、Redis、MinIO 或端口；
- 不启动本项目常驻服务，直到端口、鉴权、资源配额和密钥另行冻结；
- 供应商侧旧 API Key 与旧 Bearer Token 仍需负责人在控制台吊销/轮换；
- 无真实视频资料，当前仅验证工具链；ASR、OCR、视频编码器和 VLM 的质量验证需先取得合法样本；
- 根盘余量不适合无筛选下载大规模视频和多套模型，第一周新增数据与模型按 30 GiB 以内控制；
- 当前外部 GPU 负载很高，模型试跑需预约空闲窗口。
