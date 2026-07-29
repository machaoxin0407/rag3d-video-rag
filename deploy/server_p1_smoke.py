"""Authenticated server smoke test that never prints credentials or user media."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from video_rag.diagnosis import ffmpeg_executable


def main() -> None:
    load_dotenv()
    token = os.environ["KAFU_API_TOKEN"]
    base = os.getenv("P1_SMOKE_BASE_URL", "http://127.0.0.1:8000")
    headers = {"Authorization": f"Bearer {token}"}

    health = requests.get(f"{base}/health", timeout=10).json()
    response = requests.post(
        f"{base}/v2/chat",
        headers=headers,
        json={
            "question": "How do I set the cooking temperature and time on an air fryer?",
            "images": [],
        },
        timeout=150,
    )
    response.raise_for_status()
    chat = response.json()["data"]

    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / "smoke.mp4"
        subprocess.run(
            [
                ffmpeg_executable(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=320x240:d=3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(video_path),
            ],
            check=True,
            timeout=30,
        )
        with video_path.open("rb") as stream:
            created = requests.post(
                f"{base}/v2/video-jobs",
                headers=headers,
                files={"video": ("smoke.mp4", stream, "video/mp4")},
                data={
                    "question": "Is this air fryer operation step correct?",
                    "product_class": "Air Fryer",
                },
                timeout=30,
            )
        created.raise_for_status()
        job_id = created.json()["job_id"]
        state: dict = {}
        for _ in range(120):
            state_response = requests.get(
                f"{base}/v2/video-jobs/{job_id}",
                headers=headers,
                timeout=10,
            )
            state_response.raise_for_status()
            state = state_response.json()
            if state["status"] in {"completed", "failed"}:
                break
            time.sleep(1)
        result_response = requests.get(
            f"{base}/v2/video-jobs/{job_id}/result",
            headers=headers,
            timeout=10,
        )
        result_response.raise_for_status()
        job_result = result_response.json()
        requests.delete(
            f"{base}/v2/video-jobs/{job_id}",
            headers=headers,
            timeout=10,
        ).raise_for_status()

    print(
        json.dumps(
            {
                "status": "passed",
                "health": health["status"],
                "exact_ready": health["video_retrieval"]["exact_ready"],
                "chat": {
                    "route": chat["route"],
                    "requested_mode": chat["retrieval"]["requested_mode"],
                    "effective_mode": chat["retrieval"]["effective_mode"],
                    "videos": len(chat["videos"]),
                    "citations": len(chat["citations"]),
                    "answer_chars": len(chat["answer"]),
                },
                "video_job": {
                    "status": job_result["status"],
                    "label": (job_result.get("result") or {})
                    .get("diagnosis", {})
                    .get("label"),
                    "error": job_result.get("error"),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
