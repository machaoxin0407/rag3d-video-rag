#!/usr/bin/env python3
"""Transcribe accepted video audio with offline faster-whisper inference."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.asr import (
    DEFAULT_INPUT,
    DEFAULT_MODEL_CACHE,
    DEFAULT_RUNS,
    DEFAULT_SEGMENTS,
    transcribe_collection,
)


def parse_args() -> argparse.Namespace:
    """Parse Whisper model, device, and output manifest parameters."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--segments", type=Path, default=DEFAULT_SEGMENTS)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--device-index", type=int, default=0)
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--beam-size", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    """Run ASR and fail if any approved source did not complete."""
    args = parse_args()
    runs, segments = transcribe_collection(
        input_path=args.input,
        runs_path=args.runs,
        segments_path=args.segments,
        model_name=args.model,
        model_cache=args.model_cache,
        device=args.device,
        device_index=args.device_index,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
    )
    failures = sum(row["status"] != "success" for row in runs)
    print(
        f"transcription_complete records={len(runs)} segments={len(segments)} "
        f"failed={failures}"
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
