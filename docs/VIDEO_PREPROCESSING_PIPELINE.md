# 视频预处理流水线

该流水线把已授权并通过 A/B/C 终审的原始视频转换为后续 ASR、OCR、镜头切分和检索所需的基础产物。默认全程使用 CPU 与 FFmpeg，不申请 GPU，也不启动常驻服务。

## 输入门禁

`preprocess_video_sources.py` 只处理同时满足以下条件的记录：

1. `review_assignments.csv` 中 A、B、C 三个状态均为通过；
2. `final_decision` 为 `accept`；
3. `download_receipts.csv` 中存在下载凭证；
4. 原始文件的实际 SHA-256 与凭证一致。

任一条件不满足时，记录不会进入处理集合。已接受但缺少下载凭证时，整个运行会在处理前失败。

## 默认产物

- `data_video/processed/<record_id>/audio_16k_mono.wav`：单声道、16 kHz、PCM 音频；
- `data_video/keyframes/<record_id>/frame_*.jpg`：每 5 秒均匀抽取的基础关键帧；
- `data_video/manifests/preprocessing_manifest.csv`：源文件哈希、编解码信息、时长、分辨率、音频状态、关键帧数量和错误信息。

原始视频、音频和关键帧由 `.gitignore` 排除；只有不含媒体内容的处理清单进入 Git。

## 服务器运行

```bash
cd ~/rag3d-video
source .venv/bin/activate
python preprocess_video_sources.py --keyframe-interval 5
```

命令逐条写入清单。若某条失败，已完成条目的审计记录仍保留，命令最终以非零状态退出。重新运行会验证源文件哈希并原子替换本项目生成的对应音频与关键帧目录。

## 结果验收

```bash
python - <<'PY'
import csv
from pathlib import Path

root = Path.cwd()
manifest = root / "data_video/manifests/preprocessing_manifest.csv"
rows = list(csv.DictReader(manifest.open(encoding="utf-8")))
assert len(rows) == 11
assert all(row["status"] == "success" for row in rows)
assert sum(int(row["keyframe_count"]) for row in rows) > 0
print("preprocessing_manifest=OK")
PY
```
