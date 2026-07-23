#!/usr/bin/env python3
"""Merge the deterministic 43-video selection with the accepted Espresso gap review."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from video_rag.manifest_io import read_csv, write_csv


EXPECTED_ADDITIONS = {
    "Air Fryer": 8,
    "Espresso Machine": 3,
    "Pressure Cooker": 9,
    "Printer": 10,
    "Vacuum": 7,
    "Washing Machine": 7,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selected-43", type=Path, required=True)
    parser.add_argument("--espresso-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = read_csv(args.selected_43)
    espresso = read_csv(args.espresso_review)
    if len(selected) != 43:
        raise ValueError(f"Expected 43 selected rows, found {len(selected)}")
    if len(espresso) != 1 or espresso[0].get("record_id") != "espresso-040":
        raise ValueError("The gap review must contain only espresso-040")

    rows = [*selected, *espresso]
    record_ids = [row.get("record_id", "") for row in rows]
    if len(set(record_ids)) != 44 or "" in record_ids:
        raise ValueError("The final queue must contain 44 unique nonblank record IDs")
    source_urls = [row.get("source_page_url", "") for row in rows]
    if len(set(source_urls)) != 44 or "" in source_urls:
        raise ValueError("The final queue must contain 44 unique nonblank source URLs")

    for row in rows:
        record_id = row["record_id"]
        if row.get("review_status") != "completed":
            raise ValueError(f"{record_id}: review_status is not completed")
        if row.get("license_evidence_status") != "verified":
            raise ValueError(f"{record_id}: license evidence is not verified")
        if row.get("final_decision") != "accept":
            raise ValueError(f"{record_id}: final_decision is not accept")
        if row.get("dataset_split") not in {"development", "source_disjoint_test"}:
            raise ValueError(f"{record_id}: invalid frozen split")

    counts = Counter(row["corrected_product_class"] for row in rows)
    if dict(counts) != EXPECTED_ADDITIONS:
        raise ValueError(
            f"Final class additions differ: expected={EXPECTED_ADDITIONS} actual={dict(counts)}"
        )

    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    write_csv(args.output, fields, rows)
    print(f"finalized={len(rows)} class_counts={dict(counts)} output={args.output}")


if __name__ == "__main__":
    main()
