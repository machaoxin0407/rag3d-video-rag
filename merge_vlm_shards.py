#!/usr/bin/env python3
"""Validate and merge independent VLM shard manifests into canonical outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv
from video_rag.vlm import CAPTION_FIELDS, DEFAULT_CAPTIONS, DEFAULT_RUNS, RUN_FIELDS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenes",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "scene_manifest.csv",
    )
    parser.add_argument("--runs", type=Path, action="append", required=True)
    parser.add_argument("--captions", type=Path, action="append", required=True)
    parser.add_argument("--output-runs", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output-captions", type=Path, default=DEFAULT_CAPTIONS)
    return parser.parse_args()


def index_unique(rows: list[dict[str, str]], source: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        scene_id = row.get("scene_id", "")
        if not scene_id or scene_id in result:
            raise ValueError(f"{source}: blank or duplicate scene_id={scene_id}")
        result[scene_id] = row
    return result


def main() -> None:
    args = parse_args()
    if len(args.runs) != len(args.captions):
        raise ValueError("The number of run and caption shards differs")
    scenes = [row for row in read_csv(args.scenes) if row.get("status") == "success"]
    scene_ids = [row["scene_id"] for row in scenes]
    runs = index_unique(
        [row for path in args.runs for row in read_csv(path)], "VLM run shards"
    )
    captions = index_unique(
        [row for path in args.captions for row in read_csv(path)], "VLM caption shards"
    )
    expected = set(scene_ids)
    if set(runs) != expected:
        raise ValueError(
            f"VLM run coverage differs: missing={sorted(expected-set(runs))[:10]} "
            f"extra={sorted(set(runs)-expected)[:10]}"
        )
    if set(captions) != expected:
        raise ValueError(
            f"VLM caption coverage differs: missing={sorted(expected-set(captions))[:10]} "
            f"extra={sorted(set(captions)-expected)[:10]}"
        )
    failures = [scene_id for scene_id, row in runs.items() if row.get("status") != "success"]
    if failures:
        raise ValueError(f"Failed VLM scenes cannot be merged: {failures[:10]}")
    for scene_id in scene_ids:
        if runs[scene_id]["record_id"] != captions[scene_id]["record_id"]:
            raise ValueError(f"{scene_id}: run/caption record_id differs")

    signatures = {
        (row["model"], row["model_revision"], row["dtype"], row["prompt_version"])
        for row in runs.values()
    }
    if len(signatures) != 1:
        raise ValueError(f"VLM shards have inconsistent run signatures: {signatures}")
    ordered_runs = [runs[scene_id] for scene_id in scene_ids]
    ordered_captions = [captions[scene_id] for scene_id in scene_ids]
    write_csv(args.output_runs, RUN_FIELDS, ordered_runs)
    write_csv(args.output_captions, CAPTION_FIELDS, ordered_captions)
    print(
        f"vlm_shards_merged scenes={len(scene_ids)} failures=0 "
        f"signature={next(iter(signatures))}"
    )


if __name__ == "__main__":
    main()
