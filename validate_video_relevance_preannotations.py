#!/usr/bin/env python3
"""Strictly validate formal AI relevance labels and their provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_rag.relevance_annotation import (
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    DEFAULT_POOL,
    DEFAULT_RUNS,
    PROMPT_VERSION,
    pair_id,
    read_csv,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--labels", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pool = read_csv(args.pool)
    labels = read_csv(args.labels)
    runs = read_csv(args.runs)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected = [pair_id(row) for row in pool]
    label_ids = [
        f"{row['query_id']}|{row['candidate_scene_id']}" for row in labels
    ]
    run_ids = [row["pair_id"] for row in runs]
    if expected != label_ids or expected != run_ids:
        raise ValueError("AI artifacts do not preserve the frozen pool order")
    if len(expected) != len(set(expected)):
        raise ValueError("Duplicate query-scene pairs")
    pool_by_id = {pair_id(row): row for row in pool}
    grade_counts = {str(grade): 0 for grade in range(4)}
    for identifier, label, run in zip(expected, labels, runs):
        source = pool_by_id[identifier]
        grade = int(label["ai_relevance_grade"])
        if grade not in range(4):
            raise ValueError(f"Invalid grade: {identifier}")
        grade_counts[str(grade)] += 1
        if label["record_id"] != source["record_id"]:
            raise ValueError(f"Record mismatch: {identifier}")
        if label["prompt_version"] != PROMPT_VERSION:
            raise ValueError(f"Prompt mismatch: {identifier}")
        if label["ai_uncertainty"] not in {"low", "medium", "high"}:
            raise ValueError(f"Invalid uncertainty: {identifier}")
        if not label["ai_evidence"].strip():
            raise ValueError(f"Empty evidence: {identifier}")
        evidence_sources = set(label["ai_evidence_sources"].split("|"))
        if not evidence_sources or not evidence_sources <= {"VLM", "ASR", "OCR"}:
            raise ValueError(f"Invalid evidence sources: {identifier}")
        if grade <= 1:
            if label["ai_start_time"] or label["ai_end_time"]:
                raise ValueError(f"Low-grade pair has a time interval: {identifier}")
        else:
            start = float(label["ai_start_time"])
            end = float(label["ai_end_time"])
            if (
                start < float(source["start_seconds"]) - 0.001
                or end > float(source["end_seconds"]) + 0.001
                or end <= start
            ):
                raise ValueError(f"AI interval outside scene: {identifier}")
        if run["status"] != "success" or run["prompt_version"] != PROMPT_VERSION:
            raise ValueError(f"Failed or mismatched run: {identifier}")
        if not run["raw_output"].strip() or run["error"]:
            raise ValueError(f"Missing raw output or unexpected error: {identifier}")
    if manifest["pair_count"] != len(expected):
        raise ValueError("Run manifest pair count differs")
    if manifest["pool_sha256"] != sha256_file(args.pool):
        raise ValueError("Run manifest pool hash differs")
    if manifest["grade_counts"] != grade_counts:
        raise ValueError("Run manifest grade counts differ")
    print(
        json.dumps(
            {
                "pairs": len(expected),
                "queries": len({row["query_id"] for row in pool}),
                "scenes": len({row["candidate_scene_id"] for row in pool}),
                "grade_counts": grade_counts,
                "time_intervals": sum(
                    bool(row["ai_start_time"]) for row in labels
                ),
                "prompt_version": PROMPT_VERSION,
            },
            ensure_ascii=False,
        )
    )
    print("video_relevance_ai_validation=OK")


if __name__ == "__main__":
    main()
