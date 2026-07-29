#!/usr/bin/env python3
"""Merge non-overlapping P2 end-to-end shards into the formal 100-query result."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("shards", type=Path, nargs="+")
    args = parser.parse_args()
    rows: list[dict[str, str]] = []
    raw_by_query: dict[str, str] = {}
    for shard in args.shards:
        rows.extend(read_csv(shard / "end_to_end_per_query.csv"))
        for line in (shard / "answer_judge_raw.jsonl").read_text(
            encoding="utf-8"
        ).splitlines():
            payload = json.loads(line)
            qid = payload["query_id"]
            if qid in raw_by_query:
                raise ValueError(f"duplicate raw result: {qid}")
            raw_by_query[qid] = line
    rows.sort(key=lambda row: row["query_id"])
    query_ids = [row["query_id"] for row in rows]
    if len(rows) != 100 or len(set(query_ids)) != 100:
        raise ValueError(
            f"formal merge requires 100 unique queries, got {len(rows)} rows "
            f"and {len(set(query_ids))} IDs"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "end_to_end_per_query.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "answer_judge_raw.jsonl").write_text(
        "\n".join(raw_by_query[qid] for qid in query_ids) + "\n",
        encoding="utf-8",
    )
    metric_fields = [
        "answer_nonempty",
        "all_media_valid",
        "video_intervals_valid",
        "video_citations_resolve",
        "judge_correctness",
        "judge_evidence_support",
        "judge_video_support",
        "judge_non_hallucination",
        "judge_safety_handling",
        "judge_no_answer_handling",
    ]
    latencies = [float(row["latency_seconds"]) for row in rows]
    summary: dict[str, Any] = {
        "experiment_id": "ANS-20260729-001",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "queries": 100,
        "judge": {
            "model": json.loads(raw_by_query[query_ids[0]])["judge_model"],
            "prompt_version": json.loads(raw_by_query[query_ids[0]])[
                "prompt_version"
            ],
        },
        "metrics": {
            field: mean(float(row[field]) for row in rows)
            for field in metric_fields
        },
        "human_review_queue": sum(
            int(row["human_review_required"]) for row in rows
        ),
        "latency_seconds": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "shards": [str(path) for path in args.shards],
        "merge_validation": "100 unique query IDs; no duplicates",
        "limitations": (
            "AI judge scores are provisional. One human must review the generated "
            "failure/high-risk queue before paper claims are finalized."
        ),
    }
    (args.output / "end_to_end_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
