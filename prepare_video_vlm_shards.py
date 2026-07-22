#!/usr/bin/env python3
"""Split uncaptioned video scenes into duration-balanced VLM work shards."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv
from video_rag.scenes import SCENE_FIELDS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenes",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "scene_manifest.csv",
    )
    parser.add_argument(
        "--completed-runs",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "vlm_runs.csv",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--shards", type=int, default=2)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.shards <= 0:
        raise ValueError("--shards must be greater than zero")
    scenes = [row for row in read_csv(args.scenes) if row["status"] == "success"]
    completed = (
        {
            row["scene_id"]
            for row in read_csv(args.completed_runs)
            if row["status"] == "success"
        }
        if args.completed_runs.exists()
        else set()
    )
    known = {row["scene_id"] for row in scenes}
    unknown = sorted(completed - known)
    if unknown:
        raise ValueError(f"Completed VLM runs contain unknown scenes: {unknown}")
    order = {row["scene_id"]: index for index, row in enumerate(scenes)}
    remaining = [row for row in scenes if row["scene_id"] not in completed]
    buckets: list[list[dict[str, str]]] = [[] for _ in range(args.shards)]
    durations = [0.0] * args.shards
    for row in sorted(remaining, key=lambda item: float(item["duration_seconds"]), reverse=True):
        target = min(range(args.shards), key=lambda index: (durations[index], index))
        buckets[target].append(row)
        durations[target] += float(row["duration_seconds"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for index, bucket in enumerate(buckets):
        bucket.sort(key=lambda row: order[row["scene_id"]])
        path = args.output_dir / f"scenes_shard_{index:02d}.csv"
        write_csv(path, SCENE_FIELDS, bucket)
        print(
            f"shard={index} scenes={len(bucket)} "
            f"duration_seconds={durations[index]:.3f} path={path}",
            flush=True,
        )
    print(
        f"scene_total={len(scenes)} completed={len(completed)} "
        f"remaining={len(remaining)}"
    )


if __name__ == "__main__":
    main()
