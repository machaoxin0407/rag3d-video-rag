#!/usr/bin/env python3
"""Run repeatable retrieval, video-tool, and optional CUDA smoke checks."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VIDEO_ROOT = ROOT / "data_video"


def check_retrieval() -> dict[str, int]:
    """Load the shipped retrieval artifacts without making online API calls."""
    from retrieval_engine import RetrievalEngine

    engine = RetrievalEngine()
    engine.load_index()
    return {
        "chunks": len(engine.retrieval_chunks),
        "sections": len(engine.section_chunks),
        "products": len(engine.catalog),
        "vectors": int(engine.dense_index.ntotal) if engine.dense_index else 0,
    }


def check_video_tools(create_sample: bool) -> dict[str, object]:
    """Locate bundled FFmpeg and optionally create a tiny deterministic fixture."""
    import imageio_ffmpeg

    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    result: dict[str, object] = {
        "ffmpeg": str(ffmpeg),
        "ffmpeg_version": imageio_ffmpeg.get_ffmpeg_version(),
    }
    if not create_sample:
        return result

    video_dir = VIDEO_ROOT / "processed"
    frame_dir = VIDEO_ROOT / "keyframes"
    video_dir.mkdir(parents=True, exist_ok=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    video_path = video_dir / "week01_smoke.mp4"
    frame_path = frame_dir / "week01_smoke_001.jpg"

    subprocess.run(
        [
            str(ffmpeg), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
            "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=16000",
            "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(video_path), "-y",
        ],
        check=True,
    )
    subprocess.run(
        [
            str(ffmpeg), "-hide_banner", "-loglevel", "error",
            "-ss", "1", "-i", str(video_path),
            "-frames:v", "1", str(frame_path), "-y",
        ],
        check=True,
    )
    result.update(
        {
            "sample_video": str(video_path.relative_to(ROOT)),
            "sample_video_bytes": video_path.stat().st_size,
            "sample_frame": str(frame_path.relative_to(ROOT)),
            "sample_frame_bytes": frame_path.stat().st_size,
        }
    )
    return result


def check_cuda() -> dict[str, object]:
    """Exercise each visible GPU briefly; process exit releases all allocations."""
    import torch

    devices: list[dict[str, object]] = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            with torch.cuda.device(index):
                left = torch.randn((1024, 1024), device=f"cuda:{index}")
                right = torch.randn((1024, 1024), device=f"cuda:{index}")
                checksum = float((left @ right).mean().item())
                devices.append(
                    {
                        "index": index,
                        "name": torch.cuda.get_device_name(index),
                        "checksum": checksum,
                    }
                )
                del left, right
                torch.cuda.empty_cache()
    return {
        "torch_version": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "devices": devices,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--create-video-sample", action="store_true")
    parser.add_argument("--cuda", action="store_true")
    args = parser.parse_args()

    report: dict[str, object] = {
        "retrieval": check_retrieval(),
        "video": check_video_tools(args.create_video_sample),
    }
    if args.cuda:
        report["cuda"] = check_cuda()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
