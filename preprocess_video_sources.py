#!/usr/bin/env python3
"""Generate review-gated audio and uniform keyframes for authorized videos."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.preprocess import (
    DEFAULT_MANIFEST,
    DEFAULT_RECEIPTS,
    DEFAULT_REVIEWS,
    preprocess_collection,
)


def parse_args() -> argparse.Namespace:
    """Parse manifest locations and the uniform sampling interval."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipts", type=Path, default=DEFAULT_RECEIPTS)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--keyframe-interval", type=float, default=5.0)
    return parser.parse_args()


def main() -> None:
    """Run preprocessing and fail the command if any accepted item fails."""
    args = parse_args()
    rows = preprocess_collection(
        receipts_path=args.receipts,
        reviews_path=args.reviews,
        manifest_path=args.manifest,
        interval_seconds=args.keyframe_interval,
    )
    succeeded = sum(row["status"] == "success" for row in rows)
    failed = len(rows) - succeeded
    print(f"preprocessing_complete success={succeeded} failed={failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
