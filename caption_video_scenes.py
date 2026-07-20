#!/usr/bin/env python3
"""Generate structured bilingual visual captions for accepted video scenes."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.vlm import (
    DEFAULT_CAPTIONS,
    DEFAULT_FRAME_ROOT,
    DEFAULT_MODEL,
    DEFAULT_MODEL_CACHE,
    DEFAULT_RUNS,
    DEFAULT_SCENES,
    caption_collection,
)


def parse_args() -> argparse.Namespace:
    """Parse model, device, source, and output settings."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--captions", type=Path, default=DEFAULT_CAPTIONS)
    parser.add_argument("--frame-root", type=Path, default=DEFAULT_FRAME_ROOT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument(
        "--scene-id",
        action="append",
        default=[],
        help="Caption only the named scene; repeat for multiple scenes.",
    )
    return parser.parse_args()


def main() -> None:
    """Caption all scenes and fail when any scene did not complete."""
    args = parse_args()
    runs, captions = caption_collection(
        scenes_path=args.scenes,
        runs_path=args.runs,
        captions_path=args.captions,
        frame_root=args.frame_root,
        model_name=args.model,
        model_cache=args.model_cache,
        device=args.device,
        dtype=args.dtype,
        scene_ids=set(args.scene_id) or None,
    )
    failures = sum(row["status"] != "success" for row in runs)
    print(
        f"vlm_captioning_complete scenes={len(runs)} captions={len(captions)} "
        f"failed={failures}"
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
