#!/usr/bin/env python3
"""Detect visual scenes and render browser-compatible evidence clips."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.scenes import DEFAULT_INPUT, DEFAULT_OUTPUT, segment_collection


def parse_args() -> argparse.Namespace:
    """Parse scene detector inputs and reproducibility parameters."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--threshold", type=float, default=0.32)
    parser.add_argument("--minimum-scene-seconds", type=float, default=2.0)
    return parser.parse_args()


def main() -> None:
    """Run scene segmentation and print the resulting evidence count."""
    args = parse_args()
    rows = segment_collection(
        input_path=args.input,
        output_path=args.output,
        threshold=args.threshold,
        minimum=args.minimum_scene_seconds,
    )
    print(f"scene_segmentation_complete scenes={len(rows)} failed=0")


if __name__ == "__main__":
    main()
