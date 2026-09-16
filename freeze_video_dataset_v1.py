#!/usr/bin/env python3
"""Normalize legacy decisions and freeze the balanced six-class video dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


TARGET_CLASSES = {
    "Air Fryer",
    "Espresso Machine",
    "Pressure Cooker",
    "Printer",
    "Vacuum",
    "Washing Machine",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inventory",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "video_source_inventory.csv",
    )
    parser.add_argument(
        "--receipts",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "download_receipts.csv",
    )
    parser.add_argument(
        "--reviews",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "review_assignments.csv",
    )
    parser.add_argument(
        "--freeze-manifest",
        type=Path,
        default=ROOT
        / "data_video"
        / "manifests"
        / "video_dataset_v1_freeze_20260724.json",
    )
    parser.add_argument(
        "--split-overrides",
        type=Path,
        default=ROOT
        / "data_video"
        / "manifests"
        / "video_dataset_v1_split_overrides_20260724.csv",
    )
    parser.add_argument("--verify-hashes", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def append_note(existing: str, note: str) -> str:
    values = [value.strip() for value in existing.split(";") if value.strip()]
    if note not in values:
        values.append(note)
    return "; ".join(values)


def accepted_review(row: dict[str, str]) -> bool:
    legacy = (
        row.get("review_protocol") == "legacy_abc"
        and row.get("license_review_status") == "approved"
        and row.get("content_review_status") == "approved"
        and row.get("adjudication_status") == "approved"
    )
    single = (
        row.get("review_protocol") == "ai_single_reviewer_v1"
        and row.get("reviewer_id") == "R1"
        and row.get("review_status") == "completed"
        and row.get("license_evidence_status") == "verified"
    )
    return (legacy or single) and row.get("final_decision") == "accept"


def project_file(relative_path: str) -> Path:
    candidate = (ROOT / relative_path).resolve()
    candidate.relative_to(ROOT.resolve())
    return candidate


def main() -> None:
    args = parse_args()
    inventory = read_csv(args.inventory)
    receipts = read_csv(args.receipts)
    reviews = read_csv(args.reviews)
    inventory_fields = list(inventory[0])
    review_fields = list(reviews[0])
    receipt_by_id = {row["record_id"]: row for row in receipts}
    review_by_id = {row["record_id"]: row for row in reviews}
    target_rows = [row for row in inventory if row["product_class"] in TARGET_CLASSES]

    counts = Counter(row["product_class"] for row in target_rows)
    expected = {product_class: 13 for product_class in TARGET_CLASSES}
    if dict(counts) != expected:
        raise ValueError(f"Expected 13 videos per class: expected={expected} actual={dict(counts)}")

    ids = [row["record_id"] for row in target_rows]
    if len(set(ids)) != 78:
        raise ValueError("Frozen dataset record IDs are not unique")
    urls = [row.get("source_page_url", "") for row in target_rows]
    if "" in urls or len(set(urls)) != 78:
        raise ValueError("Frozen dataset source URLs are blank or duplicated")

    normalized_inventory = []
    legacy_normalized: list[str] = []
    for source_row in inventory:
        row = dict(source_row)
        if row["product_class"] in TARGET_CLASSES:
            record_id = row["record_id"]
            review = review_by_id.get(record_id)
            receipt = receipt_by_id.get(record_id)
            if not review or not accepted_review(review):
                raise ValueError(f"{record_id}: no completed accepted review gate")
            if not receipt:
                raise ValueError(f"{record_id}: no formal download receipt")
            if row.get("local_file_sha256") != receipt.get("sha256"):
                raise ValueError(f"{record_id}: inventory and receipt SHA-256 differ")
            if row.get("status") != "accepted":
                previous_status = row.get("status", "")
                row["notes"] = append_note(row.get("notes", ""), f"pre_freeze_status={previous_status}")
                row["status"] = "accepted"
                row["status_reason"] = "Accepted by completed review gate for balanced six-class v1 freeze"
                legacy_normalized.append(record_id)
        normalized_inventory.append(row)

    normalized_reviews = []
    for source_row in reviews:
        row = dict(source_row)
        inventory_row = next((item for item in target_rows if item["record_id"] == row["record_id"]), None)
        if inventory_row and not row.get("dataset_split"):
            if row.get("review_protocol") != "legacy_abc":
                raise ValueError(f"{row['record_id']}: non-legacy accepted row has blank split")
            row["dataset_split"] = "development"
        normalized_reviews.append(row)

    overrides = read_csv(args.split_overrides) if args.split_overrides.exists() else []
    override_by_id = {row["record_id"]: row for row in overrides}
    if len(override_by_id) != len(overrides):
        raise ValueError("Duplicate record_id in split overrides")
    normalized_target_ids = {row["record_id"] for row in target_rows}
    unknown_overrides = sorted(set(override_by_id) - normalized_target_ids)
    if unknown_overrides:
        raise ValueError(f"Split overrides contain non-target IDs: {unknown_overrides}")
    for row in normalized_reviews:
        override = override_by_id.get(row["record_id"])
        if not override:
            continue
        if row.get("dataset_split") == override.get("normalized_split"):
            continue
        if row.get("dataset_split") != override.get("original_split"):
            raise ValueError(
                f"{row['record_id']}: split override expected "
                f"{override.get('original_split')} but found {row.get('dataset_split')}"
            )
        row["dataset_split"] = override["normalized_split"]

    normalized_review_by_id = {row["record_id"]: row for row in normalized_reviews}
    creator_splits: dict[str, set[str]] = {}
    for row in target_rows:
        creator = " ".join(row.get("creator", "").lower().split())
        split = normalized_review_by_id[row["record_id"]]["dataset_split"]
        if split not in {"development", "source_disjoint_test"}:
            raise ValueError(f"{row['record_id']}: invalid frozen split={split}")
        if creator:
            creator_splits.setdefault(creator, set()).add(split)
    leakage = {creator: splits for creator, splits in creator_splits.items() if len(splits) > 1}
    if leakage:
        raise ValueError(f"Creators leak across frozen splits: {leakage}")

    if args.verify_hashes:
        for row in target_rows:
            receipt = receipt_by_id[row["record_id"]]
            source = project_file(receipt["local_path"])
            if not source.is_file():
                raise FileNotFoundError(f"{row['record_id']}: missing source file {source}")
            actual = digest(source)
            if actual != receipt["sha256"]:
                raise ValueError(f"{row['record_id']}: source SHA-256 mismatch")

    split_counts = Counter(
        normalized_review_by_id[row["record_id"]]["dataset_split"] for row in target_rows
    )
    freeze = {
        "dataset_id": "rag3d_video_v1_20260724",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "target_classes": sorted(TARGET_CLASSES),
        "video_count": len(target_rows),
        "class_counts": dict(sorted(counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "legacy_records_normalized": sorted(legacy_normalized),
        "split_overrides": overrides,
        "source_url_unique": True,
        "creator_split_leakage": False,
        "source_hashes_verified": args.verify_hashes,
    }
    if not args.dry_run:
        write_csv(args.inventory, inventory_fields, normalized_inventory)
        write_csv(args.reviews, review_fields, normalized_reviews)
        freeze["manifest_sha256"] = {
            "video_source_inventory.csv": digest(args.inventory),
            "download_receipts.csv": digest(args.receipts),
            "review_assignments.csv": digest(args.reviews),
        }
        args.freeze_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.freeze_manifest.write_text(
            json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({**freeze, "dry_run": args.dry_run}, ensure_ascii=False))


if __name__ == "__main__":
    main()
