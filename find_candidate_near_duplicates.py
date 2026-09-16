#!/usr/bin/env python3
"""Flag visually similar candidate videos from their five audit frames."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.manifest_io import ROOT, project_path, read_csv, write_csv


FIELDS = [
    "record_id_a",
    "record_id_b",
    "product_class",
    "mean_frame_hamming",
    "max_frame_hamming",
    "review_priority",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--screen",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_technical_screen.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_near_duplicates.csv",
    )
    parser.add_argument("--threshold", type=float, default=12.0)
    return parser.parse_args()


def average_hash(path: Path) -> int:
    from PIL import Image

    with Image.open(path) as image:
        values = list(image.convert("L").resize((8, 8)).getdata())
    mean = sum(values) / len(values)
    result = 0
    for index, value in enumerate(values):
        if value >= mean:
            result |= 1 << index
    return result


def signature(row: dict[str, str]) -> list[int]:
    paths = [
        project_path(value)
        for value in row["sample_frame_paths"].split("|")
        if value
    ]
    if not paths or any(not path.is_file() for path in paths):
        raise ValueError(f"Missing audit frames for {row['record_id']}")
    return [average_hash(path) for path in paths]


def main() -> None:
    args = parse_args()
    candidates = [
        row for row in read_csv(args.screen) if row["technical_decision"] == "pass"
    ]
    signatures = {row["record_id"]: signature(row) for row in candidates}
    results: list[dict[str, str]] = []
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            if left["product_class"] != right["product_class"]:
                continue
            left_hashes = signatures[left["record_id"]]
            right_hashes = signatures[right["record_id"]]
            if len(left_hashes) != len(right_hashes):
                continue
            distances = [
                (left_hash ^ right_hash).bit_count()
                for left_hash, right_hash in zip(left_hashes, right_hashes, strict=True)
            ]
            mean = sum(distances) / len(distances)
            if mean > args.threshold:
                continue
            results.append(
                {
                    "record_id_a": left["record_id"],
                    "record_id_b": right["record_id"],
                    "product_class": left["product_class"],
                    "mean_frame_hamming": f"{mean:.3f}",
                    "max_frame_hamming": str(max(distances)),
                    "review_priority": "high" if mean <= 6 else "medium",
                }
            )
    results.sort(
        key=lambda row: (float(row["mean_frame_hamming"]), row["record_id_a"])
    )
    write_csv(args.output, FIELDS, results)
    print(f"candidates={len(candidates)} similar_pairs={len(results)}")


if __name__ == "__main__":
    main()
