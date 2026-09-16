#!/usr/bin/env python3
"""Extract multilingual product text from approved video keyframes."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.ocr import (
    DEFAULT_INPUT,
    DEFAULT_OBSERVATIONS,
    DEFAULT_RUNS,
    ocr_collection,
)


def parse_args() -> argparse.Namespace:
    """Parse PaddleOCR profile, device, threshold, and manifest paths."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--language-profile", default="de")
    parser.add_argument("--ocr-version", default="PP-OCRv5")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--minimum-score", type=float, default=0.50)
    return parser.parse_args()


def main() -> None:
    """Run OCR and fail if any approved record did not complete."""
    args = parse_args()
    runs, observations = ocr_collection(
        input_path=args.input,
        runs_path=args.runs,
        observations_path=args.observations,
        language_profile=args.language_profile,
        ocr_version=args.ocr_version,
        device=args.device,
        minimum_score=args.minimum_score,
    )
    failures = sum(row["status"] != "success" for row in runs)
    print(
        f"ocr_complete records={len(runs)} observations={len(observations)} "
        f"failed={failures}"
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
