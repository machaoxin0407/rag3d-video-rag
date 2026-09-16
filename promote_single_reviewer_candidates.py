#!/usr/bin/env python3
"""Promote R1-accepted quarantine candidates into the formal video manifests."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


REVIEW_FIELDS = [
    "record_id",
    "review_protocol",
    "license_reviewer",
    "license_review_status",
    "content_reviewer",
    "content_review_status",
    "adjudicator",
    "adjudication_status",
    "reviewer_id",
    "review_status",
    "license_evidence_status",
    "final_decision",
    "dataset_split",
    "reviewed_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queue",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_review_queue.csv",
    )
    parser.add_argument("--inventory", type=Path, action="append", required=True)
    parser.add_argument("--receipts", type=Path, action="append", required=True)
    parser.add_argument(
        "--formal-inventory",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "video_source_inventory.csv",
    )
    parser.add_argument(
        "--formal-receipts",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "download_receipts.csv",
    )
    parser.add_argument(
        "--formal-reviews",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "review_assignments.csv",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def index_inputs(paths: list[Path], source: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in paths:
        for row in read_csv(path):
            record_id = row["record_id"]
            if record_id in result:
                raise ValueError(f"Duplicate {source} record: {record_id}")
            result[record_id] = row
    return result


def append_note(existing: str, note: str) -> str:
    values = [value.strip() for value in existing.split(";") if value.strip()]
    if note not in values:
        values.append(note)
    return "; ".join(values)


def normalize_legacy_inventory_row(row: dict[str, str]) -> dict[str, str]:
    """Recover notes stored in overflow columns by the legacy CSV writer."""
    result = dict(row)
    overflow = result.pop(None, [])
    for value in overflow:
        if value.strip():
            result["notes"] = append_note(result.get("notes", ""), value.strip())
    return result


def upgraded_legacy_review(row: dict[str, str]) -> dict[str, str]:
    result = {field: row.get(field, "") for field in REVIEW_FIELDS}
    result["review_protocol"] = result["review_protocol"] or "legacy_abc"
    return result


def main() -> None:
    args = parse_args()
    queue = read_csv(args.queue)
    accepted = [row for row in queue if row["final_decision"] == "accept"]
    if not accepted:
        raise ValueError("No accepted candidates to promote")
    for row in accepted:
        record_id = row["record_id"]
        if row["review_status"] != "completed":
            raise ValueError(f"{record_id}: review is incomplete")
        if row["license_evidence_status"] != "verified":
            raise ValueError(f"{record_id}: license evidence is not verified")
        if row["dataset_split"] not in {"development", "source_disjoint_test"}:
            raise ValueError(f"{record_id}: dataset split is not frozen")

    source_inventory = index_inputs(args.inventory, "inventory")
    source_receipts = index_inputs(args.receipts, "receipt")
    formal_inventory_rows = read_csv(args.formal_inventory)
    formal_receipt_rows = read_csv(args.formal_receipts)
    formal_review_rows = read_csv(args.formal_reviews)
    inventory_fields = list(formal_inventory_rows[0])
    receipt_fields = list(formal_receipt_rows[0])
    formal_inventory = {
        row["record_id"]: normalize_legacy_inventory_row(row)
        for row in formal_inventory_rows
    }
    formal_receipts = {row["record_id"]: row for row in formal_receipt_rows}
    formal_reviews = {
        row["record_id"]: upgraded_legacy_review(row) for row in formal_review_rows
    }
    for record_id, receipt in formal_receipts.items():
        inventory = formal_inventory.get(record_id)
        if not inventory:
            continue
        prior_digest = inventory.get("local_file_sha256", "")
        if prior_digest and prior_digest != receipt.get("sha256", ""):
            raise ValueError(f"{record_id}: formal inventory and receipt SHA-256 differ")
        if not prior_digest:
            inventory["local_file_sha256"] = receipt.get("sha256", "")

    for review in accepted:
        record_id = review["record_id"]
        if record_id not in source_inventory or record_id not in source_receipts:
            raise ValueError(f"{record_id}: missing candidate inventory or receipt")
        inventory = dict(source_inventory[record_id])
        receipt = dict(source_receipts[record_id])
        if inventory.get("local_file_sha256") and inventory.get(
            "local_file_sha256"
        ) != receipt.get("sha256"):
            raise ValueError(f"{record_id}: inventory and receipt SHA-256 differ")
        original_class = inventory.get("product_class", "")
        corrected_class = review["corrected_product_class"]
        inventory["product_class"] = corrected_class
        inventory["status"] = "accepted"
        inventory["status_reason"] = "AI pre-annotation accepted after completed R1 review"
        inventory["reviewer_1"] = "R1"
        inventory["reviewer_2"] = ""
        inventory["local_file_sha256"] = receipt["sha256"]
        inventory["notes"] = append_note(
            inventory.get("notes", ""),
            f"final_split={review['dataset_split']}",
        )
        inventory["notes"] = append_note(
            inventory["notes"],
            f"reviewed_at={review['reviewed_at']}",
        )
        if original_class != corrected_class:
            inventory["notes"] = append_note(
                inventory["notes"],
                f"original_product_class={original_class}",
            )
        formal_inventory[record_id] = {
            field: inventory.get(field, "") for field in inventory_fields
        }

        receipt["inventory_status"] = "accepted"
        formal_receipts[record_id] = {
            field: receipt.get(field, "") for field in receipt_fields
        }
        formal_reviews[record_id] = {
            "record_id": record_id,
            "review_protocol": "ai_single_reviewer_v1",
            "license_reviewer": "",
            "license_review_status": "",
            "content_reviewer": "",
            "content_review_status": "",
            "adjudicator": "",
            "adjudication_status": "",
            "reviewer_id": review["reviewer_id"],
            "review_status": review["review_status"],
            "license_evidence_status": review["license_evidence_status"],
            "final_decision": review["final_decision"],
            "dataset_split": review["dataset_split"],
            "reviewed_at": review["reviewed_at"],
        }

    if not args.dry_run:
        write_csv(
            args.formal_inventory,
            inventory_fields,
            sorted(formal_inventory.values(), key=lambda row: row["record_id"]),
        )
        write_csv(
            args.formal_receipts,
            receipt_fields,
            sorted(formal_receipts.values(), key=lambda row: row["record_id"]),
        )
        write_csv(
            args.formal_reviews,
            REVIEW_FIELDS,
            sorted(formal_reviews.values(), key=lambda row: row["record_id"]),
        )
    print(
        f"promoted={len(accepted)} formal_inventory={len(formal_inventory)} "
        f"formal_receipts={len(formal_receipts)} formal_reviews={len(formal_reviews)} "
        f"dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    main()
