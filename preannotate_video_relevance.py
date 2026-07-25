#!/usr/bin/env python3
"""Run one resumable GPU shard of formal video-relevance pre-annotation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_rag.relevance_annotation import (
    DEFAULT_MODEL,
    DEFAULT_MODEL_CACHE,
    DEFAULT_POOL,
    annotate_shard,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, default=2)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-new-tokens", type=int, default=220)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--allow-model-download", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = annotate_shard(
        pool_path=args.pool,
        journal_path=args.journal,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
        model_name=args.model,
        model_cache=args.model_cache,
        device=args.device,
        dtype=args.dtype,
        offline=not args.allow_model_download,
        limit=args.limit,
        max_new_tokens=args.max_new_tokens,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False))
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
