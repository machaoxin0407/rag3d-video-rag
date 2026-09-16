#!/usr/bin/env python3
"""Recover an OOM-failed scene caption from an audited same-model prescreen result."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from video_rag.manifest_io import ROOT, project_path, read_csv, write_csv
from video_rag.vlm import CAPTION_FIELDS, RUN_FIELDS, render_caption_text


RECOVERY_PROMPT_VERSION = "candidate-scope-screen-v1-derived-caption-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--scenes", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--captions", type=Path, required=True)
    parser.add_argument("--prescreen", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def index_unique(rows: list[dict[str, str]], field: str, source: str) -> dict[str, dict[str, str]]:
    result = {}
    for row in rows:
        key = row.get(field, "")
        if not key or key in result:
            raise ValueError(f"{source}: blank or duplicate {field}={key}")
        result[key] = row
    return result


def main() -> None:
    args = parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    scene_id = spec["scene_id"]
    record_id = spec["record_id"]
    scenes = read_csv(args.scenes)
    scene_order = {row["scene_id"]: index for index, row in enumerate(scenes)}
    scene = index_unique(scenes, "scene_id", "scenes").get(scene_id)
    if not scene or scene["record_id"] != record_id or scene.get("status") != "success":
        raise ValueError("Recovery scene is missing, failed, or belongs to another record")

    runs = index_unique(read_csv(args.runs), "scene_id", "runs")
    captions = index_unique(read_csv(args.captions), "scene_id", "captions")
    failed = runs.get(scene_id)
    if not failed or failed.get("status") != "failed" or "OutOfMemoryError" not in failed.get("error", ""):
        raise ValueError("Recovery is allowed only for the recorded OOM failure")
    if scene_id in captions:
        raise ValueError("A caption already exists for the recovery scene")

    prescreen = index_unique(read_csv(args.prescreen), "record_id", "prescreen").get(record_id)
    if not prescreen:
        raise ValueError("No prescreen row exists for the recovery record")
    if (
        prescreen.get("machine_decision") != "retain_for_human_review"
        or prescreen.get("predicted_product_class") != spec["catalog_product_class"]
        or prescreen.get("model") != failed.get("model")
        or prescreen.get("model_revision") != failed.get("model_revision")
        or prescreen.get("prompt_version") != "candidate-scope-screen-v1"
    ):
        raise ValueError("Prescreen evidence does not satisfy the recovery gate")
    frames = json.loads(prescreen["frame_paths_json"])
    if len(frames) < 3 or any(not project_path(path).is_file() for path in frames):
        raise ValueError("Prescreen recovery frames are missing")

    payload = {
        "summary_en": prescreen["visual_evidence"].strip(),
        "summary_zh": spec["summary_zh"].strip(),
        "product_name": spec["product_name"].strip(),
        "visible_components": spec["visible_components"],
        "visible_actions": spec["visible_actions"],
        "visible_states": spec["visible_states"],
        "safety_or_warning_text": spec["safety_or_warning_text"],
        "uncertainty": prescreen.get("uncertainty", "").strip(),
    }
    if not payload["summary_en"] or not payload["summary_zh"]:
        raise ValueError("Recovery summaries must be bilingual and nonblank")
    now = datetime.now(timezone.utc).isoformat()
    frame_json = json.dumps(frames, ensure_ascii=False, separators=(",", ":"))
    runs[scene_id] = {
        "scene_id": scene_id,
        "record_id": record_id,
        "status": "success",
        "frame_count": str(len(frames)),
        "frame_paths_json": frame_json,
        "model": prescreen["model"],
        "model_revision": prescreen["model_revision"],
        "device": "prescreen-recovery",
        "dtype": failed["dtype"],
        "prompt_version": RECOVERY_PROMPT_VERSION,
        "processed_at": now,
        "error": "",
    }
    captions[scene_id] = {
        "caption_id": f"{scene_id}-vlm-0001",
        "scene_id": scene_id,
        "record_id": record_id,
        "start_seconds": scene["start_seconds"],
        "end_seconds": scene["end_seconds"],
        "summary_en": payload["summary_en"],
        "summary_zh": payload["summary_zh"],
        "product_name": payload["product_name"],
        "catalog_product_class": spec["catalog_product_class"],
        "visible_components_json": json.dumps(payload["visible_components"], ensure_ascii=False, separators=(",", ":")),
        "visible_actions_json": json.dumps(payload["visible_actions"], ensure_ascii=False, separators=(",", ":")),
        "visible_states_json": json.dumps(payload["visible_states"], ensure_ascii=False, separators=(",", ":")),
        "safety_or_warning_text_json": json.dumps(payload["safety_or_warning_text"], ensure_ascii=False, separators=(",", ":")),
        "uncertainty": payload["uncertainty"],
        "caption_text": render_caption_text(payload),
        "model": prescreen["model"],
        "model_revision": prescreen["model_revision"],
        "prompt_version": RECOVERY_PROMPT_VERSION,
        "frame_paths_json": frame_json,
        "review_status": "pending",
    }
    write_csv(args.runs, RUN_FIELDS, sorted(runs.values(), key=lambda row: scene_order[row["scene_id"]]))
    write_csv(args.captions, CAPTION_FIELDS, sorted(captions.values(), key=lambda row: scene_order[row["scene_id"]]))
    audit = {
        "schema_version": "vlm-prescreen-recovery-v1",
        "created_at": now,
        "scene_id": scene_id,
        "record_id": record_id,
        "recovery_reason": "Primary three-frame scene caption failed with CUDA OOM on a 2160x3840 source; reused successful five-frame output from the same pinned model and revision.",
        "original_error": failed["error"],
        "source_prescreen_prompt_version": prescreen["prompt_version"],
        "recovery_prompt_version": RECOVERY_PROMPT_VERSION,
        "model": prescreen["model"],
        "model_revision": prescreen["model_revision"],
        "source_frame_count": len(frames),
        "prescreen_sha256": sha256(args.prescreen),
        "recovery_spec_sha256": sha256(args.spec),
        "human_video_review": spec["human_video_review"],
    }
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
