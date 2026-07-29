"""Bounded asynchronous user-video diagnosis for the P1 product API."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOB_ROOT = ROOT / "data_video" / "work" / "user_jobs"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v"}
ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "application/octet-stream",
}


def ffmpeg_executable() -> str:
    """Use system FFmpeg when present, otherwise the pinned user-space binary."""
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


class VideoJobManager:
    """Persist job state on disk so a single-worker restart is inspectable."""

    def __init__(self, root: Path = DEFAULT_JOB_ROOT) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, filename: str, content_type: str, question: str, product_class: str) -> tuple[str, Path]:
        suffix = Path(filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError(f"unsupported video extension: {suffix or '(none)'}")
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"unsupported content type: {content_type}")
        job_id = f"vjob_{uuid.uuid4().hex}"
        job_dir = (self.root / job_id).resolve()
        job_dir.mkdir(parents=False)
        input_path = job_dir / f"input{suffix}"
        self._write_state(
            job_id,
            {
                "job_id": job_id,
                "status": "uploading",
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
                "question": question.strip(),
                "product_class": product_class.strip(),
                "input_file": input_path.name,
                "error": None,
                "result": None,
            },
        )
        return job_id, input_path

    def get(self, job_id: str) -> dict[str, Any]:
        state_path = self._state_path(job_id)
        if not state_path.is_file():
            raise KeyError(job_id)
        return json.loads(state_path.read_text(encoding="utf-8"))

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            state = self.get(job_id)
            state.update(changes)
            state["updated_at"] = int(time.time())
            self._state_path(job_id).write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return state

    def delete(self, job_id: str) -> None:
        job_dir = self._job_dir(job_id)
        if not (job_dir / "state.json").is_file():
            raise KeyError(job_id)
        shutil.rmtree(job_dir)

    def claim_next(self) -> str | None:
        """Atomically claim one queued job for a separate worker process."""
        with self._lock:
            for state_path in sorted(self.root.glob("vjob_*/state.json")):
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if state.get("status") != "queued":
                    continue
                state["status"] = "claimed"
                state["updated_at"] = int(time.time())
                state_path.write_text(
                    json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return str(state["job_id"])
        return None

    def _job_dir(self, job_id: str) -> Path:
        if not job_id.startswith("vjob_") or not job_id[5:].isalnum():
            raise KeyError(job_id)
        path = (self.root / job_id).resolve()
        if self.root not in path.parents:
            raise KeyError(job_id)
        return path

    def _state_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "state.json"

    def _write_state(self, job_id: str, state: dict[str, Any]) -> None:
        self._state_path(job_id).write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def probe_video(path: Path) -> dict[str, Any]:
    """Validate actual media using ffprobe, not the caller-supplied MIME type."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        import imageio_ffmpeg

        reader = imageio_ffmpeg.read_frames(str(path))
        try:
            payload = next(reader)
        finally:
            reader.close()
        width, height = payload.get("size") or (0, 0)
        duration = float(payload.get("duration") or 0)
        codec = payload.get("codec")
        return _validate_video_metadata(path, duration, int(width), int(height), codec)
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
    payload = json.loads(completed.stdout)
    streams = [stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"]
    if not streams:
        raise ValueError("uploaded file has no video stream")
    stream = streams[0]
    duration = float(payload.get("format", {}).get("duration") or stream.get("duration") or 0)
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    return _validate_video_metadata(
        path,
        duration,
        width,
        height,
        stream.get("codec_name"),
    )


def _validate_video_metadata(
    path: Path,
    duration: float,
    width: int,
    height: int,
    codec: str | None,
) -> dict[str, Any]:
    max_duration = float(os.getenv("USER_VIDEO_MAX_DURATION_S", "60"))
    max_pixels = int(os.getenv("USER_VIDEO_MAX_PIXELS", str(3840 * 2160)))
    if duration <= 0 or duration > max_duration:
        raise ValueError(f"video duration must be within (0, {max_duration}] seconds")
    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise ValueError("video resolution exceeds the configured limit")
    return {
        "duration_seconds": round(duration, 3),
        "width": width,
        "height": height,
        "codec": codec,
        "size_bytes": path.stat().st_size,
    }


def extract_keyframes(
    path: Path,
    output_dir: Path,
    *,
    duration_seconds: float,
    count: int = 6,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame_%02d.jpg"
    command = [
        ffmpeg_executable(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vf",
        f"fps={count / max(duration_seconds, 0.001):.8f},scale='min(960,iw)':-2",
        "-frames:v",
        str(count),
        "-q:v",
        "3",
        str(pattern),
    ]
    subprocess.run(command, capture_output=True, text=True, timeout=60, check=True)
    frames = sorted(output_dir.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError("no diagnostic frames were extracted")
    return frames


def _vision_diagnosis(
    frames: list[Path],
    *,
    question: str,
    product_class: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    base_url = os.getenv("USER_VIDEO_VLM_BASE_URL", "").strip()
    api_key = os.getenv("USER_VIDEO_VLM_API_KEY", "").strip()
    model = os.getenv("USER_VIDEO_VLM_MODEL", "").strip()
    if not (base_url and api_key and model):
        return (
            {
                "label": "insufficient_evidence",
                "current_step": None,
                "deviation_type": None,
                "next_action": "配置 USER_VIDEO_VLM_* 后重新分析；当前仅完成媒体校验和关键帧提取。",
                "confidence": 0.0,
                "evidence": [],
                "safety_note": "未运行视觉模型，因此不对操作是否正确作推断。",
            },
            {"provider": "none", "model": "", "fallback": "vlm_not_configured"},
        )

    from openai import OpenAI

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "你是产品操作视频诊断器。只依据给定的有序关键帧判断，不可臆测不可见步骤。"
                "输出严格 JSON，字段为 label(correct_step|wrong_order|missing_step|wrong_component|"
                "unsafe_action|device_state_mismatch|insufficient_evidence|out_of_scope)、"
                "current_step、deviation_type、next_action、confidence(0-1)、"
                "evidence(数组，每项含 frame 与 observation)、safety_note。"
                f"\n用户问题：{question or '未提供'}\n产品类别：{product_class or '未知'}"
            ),
        }
    ]
    for frame in frames:
        encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
            }
        )
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=90, max_retries=1)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    result = json.loads(response.choices[0].message.content or "{}")
    required = {"label", "current_step", "deviation_type", "next_action", "confidence", "evidence", "safety_note"}
    if not required.issubset(result):
        raise ValueError("vision model returned an incomplete diagnosis")
    if result["label"] not in {
        "correct_step",
        "wrong_order",
        "missing_step",
        "wrong_component",
        "unsafe_action",
        "device_state_mismatch",
        "insufficient_evidence",
        "out_of_scope",
    }:
        raise ValueError("vision model returned an invalid label")
    return result, {"provider": "openai_compatible", "model": model}


def run_diagnosis_job(manager: VideoJobManager, job_id: str, retriever: Any | None = None) -> None:
    """Execute a job in a background worker and always persist terminal state."""
    try:
        state = manager.update(job_id, status="validating")
        input_path = manager._job_dir(job_id) / state["input_file"]
        metadata = probe_video(input_path)
        manager.update(job_id, status="analyzing", media=metadata)
        frames = extract_keyframes(
            input_path,
            manager._job_dir(job_id) / "frames",
            duration_seconds=metadata["duration_seconds"],
        )
        diagnosis, model_info = _vision_diagnosis(
            frames,
            question=state.get("question", ""),
            product_class=state.get("product_class", ""),
        )
        query = " ".join(
            part for part in (state.get("product_class", ""), state.get("question", "")) if part
        )
        standards: list[dict[str, Any]] = []
        if retriever is not None and query:
            for item in retriever.search(query, top_k=3):
                standards.append(item.to_dict())
        manager.update(
            job_id,
            status="completed",
            result={
                "diagnosis": diagnosis,
                "media": metadata,
                "sampled_frames": [f"frames/{path.name}" for path in frames],
                "matched_standard_scenes": standards,
                "model": model_info,
            },
        )
    except Exception as exc:  # noqa: BLE001 - background failures must be queryable
        manager.update(job_id, status="failed", error=str(exc)[:1000])
