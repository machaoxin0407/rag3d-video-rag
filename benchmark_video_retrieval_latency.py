#!/usr/bin/env python3
"""Measure warm single-query latency for the configured video retriever."""

from __future__ import annotations

import argparse
import json
import statistics
import time

from video_rag.retrieval import VideoEvidenceRetriever


def main() -> None:
    """Run a warm single-query benchmark and print JSON metrics."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["bm25", "dense", "visual", "hybrid", "tri_hybrid"],
        default="hybrid",
    )
    parser.add_argument("--runs", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=2)
    args = parser.parse_args()
    if args.runs <= args.warmup:
        raise SystemExit("--runs must exceed --warmup")

    retriever = VideoEvidenceRetriever(mode=args.mode)
    query = "Which espresso-machine clip shows coffee flowing into a blue mug?"
    timings: list[float] = []
    results = []
    for _ in range(args.runs):
        started = time.perf_counter()
        results = retriever.search(query, top_k=3)
        timings.append((time.perf_counter() - started) * 1000)
    measured = sorted(timings[args.warmup :])
    p95_index = max(0, int(len(measured) * 0.95) - 1)
    report = {
        "requested_mode": args.mode,
        "effective_mode": results[0].retrieval_mode if results else None,
        "runs": args.runs,
        "warmup": args.warmup,
        "median_ms": round(statistics.median(measured), 3),
        "p95_ms": round(measured[p95_index], 3),
        "top_scene_ids": [item.scene_id for item in results],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
