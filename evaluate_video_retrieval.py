#!/usr/bin/env python3
"""Compare retrieval modes on a small, explicitly provisional seed query set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_rag.retrieval import VideoEvidenceRetriever


# These labels exercise the system before the three-person relevance judgments
# are complete. They are regression checks, not publishable evaluation results.
SEED_CASES: list[tuple[str, str]] = [
    ("数码相机内部哪一段能看到橙色柔性排线和紫色芯片？", "camera-001-scene-0006"),
    ("Show the camera scene with two cameras placed on a blue table.", "camera-001-scene-0003"),
    ("咖啡机压实手柄中咖啡粉的画面", "espresso-001-scene-0007"),
    ("Which espresso-machine clip shows coffee flowing into a blue mug?", "espresso-002-scene-0001"),
    ("意式咖啡机旁边放着一杯已完成的浓缩咖啡", "espresso-001-scene-0002"),
    ("压力锅阀门持续冒蒸汽的状态", "pressure-001-scene-0001"),
    ("Show the printer while paper and the finished image emerge.", "printer-001-scene-0001"),
    ("吸尘器软管和附件放在图案地毯上", "vacuum-002-scene-0001"),
    ("Which washing-machine scene has a digital countdown display?", "washing-003-scene-0001"),
]


def parse_args() -> argparse.Namespace:
    """Parse retrieval modes and regression-report options."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["bm25", "dense", "hybrid"],
        choices=["bm25", "dense", "hybrid"],
    )
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-dense",
        action="store_true",
        help="Fail if dense or hybrid requests silently fall back to BM25.",
    )
    return parser.parse_args()


def evaluate_mode(mode: str, top_k: int) -> dict[str, object]:
    """Calculate provisional ranking metrics for one retrieval mode."""
    retriever = VideoEvidenceRetriever(mode=mode)
    rows: list[dict[str, object]] = []
    reciprocal_ranks: list[float] = []
    hit_at_1 = 0
    hit_at_k = 0
    effective_modes: set[str] = set()
    for query, expected_scene_id in SEED_CASES:
        results = retriever.search(query, top_k=top_k)
        returned_ids = [item.scene_id for item in results]
        effective_modes.update(item.retrieval_mode for item in results)
        rank = (
            returned_ids.index(expected_scene_id) + 1
            if expected_scene_id in returned_ids
            else None
        )
        reciprocal_ranks.append(1.0 / rank if rank is not None else 0.0)
        hit_at_1 += int(rank == 1)
        hit_at_k += int(rank is not None)
        rows.append(
            {
                "query": query,
                "expected_scene_id": expected_scene_id,
                "returned_scene_ids": returned_ids,
                "rank": rank,
            }
        )
    count = len(SEED_CASES)
    return {
        "requested_mode": mode,
        "effective_modes": sorted(effective_modes),
        "seed_query_count": count,
        "hit_at_1": hit_at_1 / count,
        f"hit_at_{top_k}": hit_at_k / count,
        "mrr_at_k": sum(reciprocal_ranks) / count,
        "cases": rows,
    }


def main() -> None:
    """Evaluate requested modes and optionally persist the JSON report."""
    args = parse_args()
    report = {
        "label_status": "provisional_seed_queries_not_human_ground_truth",
        "top_k": args.top_k,
        "modes": [evaluate_mode(mode, args.top_k) for mode in args.modes],
    }
    if args.require_dense:
        for result in report["modes"]:
            requested = result["requested_mode"]
            if requested in {"dense", "hybrid"} and requested not in result["effective_modes"]:
                raise SystemExit(f"{requested} retrieval fell back instead of using dense scores")
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
