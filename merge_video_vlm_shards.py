#!/usr/bin/env python3
"""Merge and validate VLM scene-caption shards into canonical manifests."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.manifest_io import read_csv, write_csv
from video_rag.vlm import (
    CAPTION_FIELDS,
    DEFAULT_CAPTIONS,
    DEFAULT_RUNS,
    DEFAULT_SCENES,
    RUN_FIELDS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=Path, default=DEFAULT_SCENES)
    parser.add_argument("--runs", type=Path, action="append", required=True)
    parser.add_argument("--captions", type=Path, action="append", required=True)
    parser.add_argument("--output-runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output-captions", type=Path, default=DEFAULT_CAPTIONS)
    return parser.parse_args()


def index_unique(paths: list[Path], key: str, source: str) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for path in paths:
        for row in read_csv(path):
            identifier = row[key]
            if identifier in indexed:
                raise ValueError(f"Duplicate {source}: {identifier}")
            indexed[identifier] = row
    return indexed


def main() -> None:
    args = parse_args()
    scenes = [row for row in read_csv(args.scenes) if row["status"] == "success"]
    order = [row["scene_id"] for row in scenes]
    expected = set(order)
    runs = index_unique(args.runs, "scene_id", "VLM run")
    captions = index_unique(args.captions, "scene_id", "VLM caption")
    if set(runs) != expected:
        raise ValueError(
            f"VLM run coverage differs: missing={sorted(expected-set(runs))} "
            f"extra={sorted(set(runs)-expected)}"
        )
    if set(captions) != expected:
        raise ValueError(
            f"VLM caption coverage differs: missing={sorted(expected-set(captions))} "
            f"extra={sorted(set(captions)-expected)}"
        )
    failed = [scene_id for scene_id, row in runs.items() if row["status"] != "success"]
    if failed:
        raise ValueError(f"Failed VLM runs cannot be merged: {failed}")
    for scene_id in order:
        if runs[scene_id]["record_id"] != captions[scene_id]["record_id"]:
            raise ValueError(f"VLM record mismatch: {scene_id}")
    write_csv(args.output_runs, RUN_FIELDS, [runs[scene_id] for scene_id in order])
    write_csv(
        args.output_captions,
        CAPTION_FIELDS,
        [captions[scene_id] for scene_id in order],
    )
    print(f"merged_vlm_scenes={len(order)} failed=0")


if __name__ == "__main__":
    main()
