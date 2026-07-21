#!/usr/bin/env python3
"""Merge non-overlapping VLM screening shards into one validated manifest."""

from __future__ import annotations

import argparse
from pathlib import Path

from classify_video_candidates import FIELDS
from video_rag.manifest_io import ROOT, read_csv, write_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--technical-screen",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_technical_screen.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_content_screen.csv",
    )
    parser.add_argument("--require-complete", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    expected = [
        row["record_id"]
        for row in read_csv(args.technical_screen)
        if row["technical_decision"] == "pass"
    ]
    merged: dict[str, dict[str, str]] = {}
    for path in args.inputs:
        for row in read_csv(path):
            record_id = row["record_id"]
            if record_id in merged and row != merged[record_id]:
                raise ValueError(f"Conflicting duplicate content row: {record_id}")
            merged[record_id] = row
    unexpected = set(merged) - set(expected)
    if unexpected:
        raise ValueError(f"Unexpected content rows: {sorted(unexpected)}")
    missing = set(expected) - set(merged)
    if args.require_complete and missing:
        raise ValueError(f"Missing content rows: {sorted(missing)}")
    rows = [merged[record_id] for record_id in expected if record_id in merged]
    write_csv(args.output, FIELDS, rows)
    decisions: dict[str, int] = {}
    for row in rows:
        decision = row["machine_decision"]
        decisions[decision] = decisions.get(decision, 0) + 1
    print(
        f"merged={len(rows)} expected={len(expected)} missing={len(missing)} "
        f"decisions={decisions}"
    )


if __name__ == "__main__":
    main()
