#!/usr/bin/env python3
"""Merge complete AI relevance journals into canonical paper artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_rag.relevance_annotation import (
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    DEFAULT_POOL,
    DEFAULT_RUNS,
    merge_journals,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--journal", action="append", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = merge_journals(
        pool_path=args.pool,
        journals=args.journal,
        labels_path=args.labels,
        runs_path=args.runs,
        manifest_path=args.manifest,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("video_relevance_ai_merge=OK")


if __name__ == "__main__":
    main()
