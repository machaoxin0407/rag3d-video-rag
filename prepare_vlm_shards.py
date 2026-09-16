#!/usr/bin/env python3
"""Create deterministic, approximately balanced scene manifests for VLM workers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenes",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "scene_manifest.csv",
    )
    parser.add_argument("--shards", type=int, default=2)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data_video" / "work" / "vlm_shards",
    )
    return parser.parse_args()


def estimated_frames(row: dict[str, str]) -> int:
    duration = float(row["end_seconds"]) - float(row["start_seconds"])
    return 1 if duration < 3 else 2 if duration < 8 else 3


def main() -> None:
    args = parse_args()
    if args.shards < 1:
        raise ValueError("--shards must be positive")
    rows = [row for row in read_csv(args.scenes) if row.get("status") == "success"]
    if not rows:
        raise ValueError("No successful scenes to shard")
    fields = list(rows[0])
    original_order = {row["scene_id"]: index for index, row in enumerate(rows)}
    assignments: list[list[dict[str, str]]] = [[] for _ in range(args.shards)]
    loads = [0 for _ in range(args.shards)]
    for row in sorted(rows, key=lambda item: (-estimated_frames(item), item["scene_id"])):
        shard = min(range(args.shards), key=lambda index: (loads[index], index))
        assignments[shard].append(row)
        loads[shard] += estimated_frames(row)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"scene_count": len(rows), "shards": []}
    for index, shard_rows in enumerate(assignments):
        shard_rows.sort(key=lambda row: original_order[row["scene_id"]])
        path = args.output_dir / f"scenes_shard_{index}.csv"
        write_csv(path, fields, shard_rows)
        summary["shards"].append(
            {
                "shard": index,
                "scene_count": len(shard_rows),
                "estimated_frame_count": loads[index],
                "path": str(path),
            }
        )
    (args.output_dir / "shard_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
