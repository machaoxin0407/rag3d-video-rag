#!/usr/bin/env python3
"""Use a pinned local VLM to triage technically valid candidate videos."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from video_rag.manifest_io import ROOT, project_path, read_csv, write_csv
from video_rag.vlm import generate_text


DEFAULT_MODEL = "Qwen/Qwen3-VL-8B-Instruct"
FIELDS = [
    "record_id",
    "expected_product_class",
    "title",
    "target_visible",
    "predicted_product_class",
    "procedure_relevance",
    "functional_step_visible",
    "visual_evidence",
    "uncertainty",
    "machine_decision",
    "model",
    "model_revision",
    "prompt_version",
    "frame_paths_json",
    "processed_at",
    "error",
]
PROMPT_VERSION = "candidate-scope-screen-v1"
VALID_VISIBILITY = {"yes", "no", "uncertain"}
VALID_RELEVANCE = {
    "operation",
    "setup",
    "maintenance",
    "troubleshooting",
    "component_overview",
    "manufacturing",
    "promotion",
    "irrelevant",
    "uncertain",
}
VALID_DECISIONS = {"retain_for_human_review", "reject_out_of_scope", "manual_review"}


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
        default=ROOT / "data_video" / "manifests" / "candidate_content_screen.csv",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--model-cache", type=Path, default=ROOT / "models" / "qwen3-vl-8b"
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--record-id", action="append")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def prompt_for(expected_class: str, title: str) -> str:
    scope = """
The target taxonomy contains exactly six household product classes:
- Air Fryer: a standalone basket/oven air fryer. A combination appliance is
  uncertain unless its distinct air-fry hardware or mode is visible.
- Espresso Machine: a machine that extracts espresso. Exclude drip coffee
  makers, coffee beans, and beverage-only scenes.
- Pressure Cooker: stovetop or electric pressure cookers and multicookers
  visibly demonstrating pressure-cooking hardware or controls.
- Washing Machine: household laundry washers. Exclude pressure washers,
  hand-washing, animal washing, and films whose title contains "washing".
- Vacuum: household floor, handheld, backpack, wet/dry, or robot vacuum
  cleaners. Exclude vacuum sealers, laboratory/space vacuum systems and dams.
- Printer: paper, photo, label, or office printers. Exclude 3D printers and
  unrelated printing exhibitions.
""".strip()
    schema = """
Return exactly one JSON object and no Markdown:
{
  "target_visible": "yes|no|uncertain",
  "predicted_product_class": "one taxonomy class, other, or uncertain",
  "procedure_relevance": "operation|setup|maintenance|troubleshooting|component_overview|manufacturing|promotion|irrelevant|uncertain",
  "functional_step_visible": "yes|no|uncertain",
  "visual_evidence": "short description of visible evidence",
  "uncertainty": "short description or empty string",
  "machine_decision": "retain_for_human_review|reject_out_of_scope|manual_review"
}
Retain only when the expected target product is visibly supported and at least
one useful operation, setup, maintenance, troubleshooting, or component step
is visible. Reject obvious wrong-domain material. Use manual_review whenever
the sparse frames cannot support a confident retain or reject decision.
""".strip()
    return (
        "You are screening five ordered frames sampled from one quarantined "
        "video. Base the decision on visible evidence, not the source title.\n\n"
        f"Expected catalog class: {expected_class}\n"
        f"Untrusted source title (context only): {title}\n\n{scope}\n\n{schema}"
    )


def parse_payload(text: str) -> dict[str, str]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1]).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model output contains no JSON object")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("model output is not an object")
    required = {
        "target_visible",
        "predicted_product_class",
        "procedure_relevance",
        "functional_step_visible",
        "visual_evidence",
        "uncertainty",
        "machine_decision",
    }
    if set(payload) != required or any(not isinstance(payload[key], str) for key in required):
        raise ValueError("model output has invalid fields or field types")
    if payload["target_visible"] not in VALID_VISIBILITY:
        raise ValueError("invalid target_visible")
    if payload["functional_step_visible"] not in VALID_VISIBILITY:
        raise ValueError("invalid functional_step_visible")
    if payload["procedure_relevance"] not in VALID_RELEVANCE:
        raise ValueError("invalid procedure_relevance")
    if payload["machine_decision"] not in VALID_DECISIONS:
        raise ValueError("invalid machine_decision")
    return {key: payload[key].strip() for key in required}


def frame_paths(row: dict[str, str]) -> list[Path]:
    values = [value for value in row["sample_frame_paths"].split("|") if value]
    paths = [project_path(value) for value in values]
    if not paths or any(not path.is_file() for path in paths):
        raise ValueError("candidate review frames are missing")
    return paths


def failed_row(
    row: dict[str, str], model: str, revision: str, error: Exception
) -> dict[str, str]:
    result = {field: "" for field in FIELDS}
    result.update(
        {
            "record_id": row["record_id"],
            "expected_product_class": row["product_class"],
            "title": row["title"],
            "machine_decision": "manual_review",
            "model": model,
            "model_revision": revision,
            "prompt_version": PROMPT_VERSION,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(error).__name__}: {error}",
        }
    )
    return result


def main() -> None:
    args = parse_args()
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    rows = [row for row in read_csv(args.screen) if row["technical_decision"] == "pass"]
    if args.record_id:
        selected = set(args.record_id)
        rows = [row for row in rows if row["record_id"] in selected]
        missing = selected - {row["record_id"] for row in rows}
        if missing:
            raise ValueError(f"Unknown or technically failed records: {sorted(missing)}")
    if args.offset < 0:
        raise ValueError("--offset cannot be negative")
    if args.offset:
        rows = rows[args.offset :]
    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError("--limit must be greater than zero")
        rows = rows[: args.limit]
    prior = {
        row["record_id"]: row for row in read_csv(args.output)
    } if args.output.exists() else {}

    dtype_value = getattr(torch, args.dtype)
    args.model_cache.mkdir(parents=True, exist_ok=True)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model,
        cache_dir=args.model_cache,
        dtype=dtype_value,
        device_map=args.device,
        low_cpu_mem_usage=True,
    )
    processor = AutoProcessor.from_pretrained(args.model, cache_dir=args.model_cache)
    revision = str(getattr(model.config, "_commit_hash", "") or "unresolved")
    output_rows = dict(prior)
    for index, row in enumerate(rows, start=1):
        record_id = row["record_id"]
        existing = prior.get(record_id)
        if existing and not existing.get("error"):
            print(f"[{index}/{len(rows)}] skipped={record_id}", flush=True)
            continue
        try:
            frames = frame_paths(row)
            raw = generate_text(
                model,
                processor,
                frames,
                prompt_for(row["product_class"], row["title"]),
            )
            payload = parse_payload(raw)
            relative_frames = [
                str(path.relative_to(ROOT)).replace("\\", "/") for path in frames
            ]
            result = {
                "record_id": record_id,
                "expected_product_class": row["product_class"],
                "title": row["title"],
                **payload,
                "model": args.model,
                "model_revision": revision,
                "prompt_version": PROMPT_VERSION,
                "frame_paths_json": json.dumps(
                    relative_frames, ensure_ascii=False, separators=(",", ":")
                ),
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "error": "",
            }
        except Exception as exc:  # Preserve audit row and continue the batch.
            result = failed_row(row, args.model, revision, exc)
        output_rows[record_id] = result
        write_csv(args.output, FIELDS, list(output_rows.values()))
        print(
            f"[{index}/{len(rows)}] {result['machine_decision']}={record_id}"
            f" error={result['error'] or 'none'}",
            flush=True,
        )
    decisions: dict[str, int] = {}
    for row in output_rows.values():
        decision = row["machine_decision"]
        decisions[decision] = decisions.get(decision, 0) + 1
    print(f"classified={len(output_rows)} decisions={decisions}")


if __name__ == "__main__":
    main()
