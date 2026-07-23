#!/usr/bin/env python3
"""Validate the 44-video expansion hand-off and frozen 100-query design."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import zipfile
from collections import Counter
from pathlib import Path

from video_rag.retrieval import PRODUCT_ALIASES


ROOT = Path(__file__).resolve().parent
MANIFEST_DIR = ROOT / "data_video" / "manifests"


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def unique_ids(rows: list[dict[str, str]], label: str) -> set[str]:
    ids = [row["record_id"] for row in rows]
    require(len(ids) == len(set(ids)), f"{label} contains duplicate record_id values")
    return set(ids)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_identity(path: Path) -> tuple[int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size


def detected_products(query: str) -> set[str]:
    normalized = query.casefold().replace("-", " ").replace("_", " ").replace("/", " ")
    detected: set[str] = set()
    for product_class, aliases in PRODUCT_ALIASES.items():
        if any(alias.casefold().replace("-", " ") in normalized for alias in aliases):
            detected.add(product_class)
    return detected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=Path.home() / "Desktop" / "single_reviewer_bundle_expansion_20260723",
    )
    parser.add_argument(
        "--verify-hashes",
        action="store_true",
        help="Recompute raw and bundle video SHA-256 values (slower).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bundle_dir = args.bundle_dir.resolve()

    inventory = load_csv(MANIFEST_DIR / "archive_candidates.csv")
    receipts = load_csv(MANIFEST_DIR / "archive_candidate_download_receipts.csv")
    technical = load_csv(MANIFEST_DIR / "archive_candidate_technical_screen.csv")
    content = load_csv(MANIFEST_DIR / "archive_candidate_content_screen.csv")
    queue = load_csv(MANIFEST_DIR / "candidate_review_queue_expansion_20260723.csv")
    queries = load_csv(MANIFEST_DIR / "paper_video_queries_v1.csv")

    inventory_ids = unique_ids(inventory, "archive inventory")
    receipt_ids = unique_ids(receipts, "download receipts")
    technical_ids = unique_ids(technical, "technical screen")
    content_ids = unique_ids(content, "content screen")
    queue_ids = unique_ids(queue, "R1 queue")

    require(len(inventory) == 157, "archive inventory must contain 157 candidates")
    require(receipt_ids == inventory_ids, "download receipts and inventory IDs differ")
    require(technical_ids == inventory_ids, "technical screen and inventory IDs differ")

    technical_counts = Counter(row["technical_decision"] for row in technical)
    require(technical_counts == {"pass": 149, "fail": 8}, f"unexpected technical counts: {technical_counts}")
    technical_pass_ids = {
        row["record_id"] for row in technical if row["technical_decision"] == "pass"
    }
    require(content_ids == technical_pass_ids, "content screen must cover every technical pass exactly once")
    content_counts = Counter(row["machine_decision"] for row in content)
    expected_content = {
        "retain_for_human_review": 123,
        "reject_out_of_scope": 25,
        "manual_review": 1,
    }
    require(content_counts == expected_content, f"unexpected AI content counts: {content_counts}")

    require(len(queue) == 121, "R1 queue must contain 121 rows")
    require(queue_ids <= content_ids, "R1 queue contains an ID absent from AI content screening")
    scope_counts = Counter(row["review_scope"] for row in queue)
    require(
        scope_counts == {"full_positive_review": 115, "rejected_audit_sample": 6},
        f"unexpected R1 scope counts: {scope_counts}",
    )
    priority_counts = Counter(row["review_priority"] for row in queue)
    require(
        priority_counts == {"normal": 98, "high": 17, "audit": 6},
        f"unexpected R1 priority counts: {priority_counts}",
    )
    positive_class_counts = Counter(
        row["ai_expected_product_class"]
        for row in queue
        if row["review_scope"] == "full_positive_review"
    )
    expected_positive_classes = {
        "Air Fryer": 10,
        "Espresso Machine": 5,
        "Pressure Cooker": 15,
        "Printer": 19,
        "Vacuum": 32,
        "Washing Machine": 34,
    }
    require(
        positive_class_counts == expected_positive_classes,
        f"unexpected positive R1 class counts: {positive_class_counts}",
    )

    for name in ("index.html", "README.md", "review_form.csv", "source_queue_snapshot.csv", "bundle_manifest.csv"):
        require((bundle_dir / name).is_file(), f"bundle file missing: {name}")
    workbook = bundle_dir / "R1_video_review_workbook.xlsx"
    require(workbook.is_file(), "R1 workbook is missing")
    with zipfile.ZipFile(workbook) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8", errors="replace")
        for sheet_name in ("Progress", "Instructions", "Validation_Lists", "Review_Form", "Field_Reference"):
            require(sheet_name in workbook_xml, f"R1 workbook sheet missing: {sheet_name}")
        worksheet_xml = [
            archive.read(name).decode("utf-8", errors="replace")
            for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        ]
        validation_rule_count = sum(xml.count("<x:dataValidation ") for xml in worksheet_xml)
        require(validation_rule_count == 8, f"R1 workbook must contain eight dropdown rules, found {validation_rule_count}")
        formula_errors = ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?")
        require(not any(error in xml for xml in worksheet_xml for error in formula_errors), "R1 workbook contains formula errors")

    bundle_manifest = load_csv(bundle_dir / "bundle_manifest.csv")
    bundle_ids = unique_ids(bundle_manifest, "bundle manifest")
    require(bundle_ids == queue_ids, "bundle manifest and R1 queue IDs differ")

    receipt_by_id = {row["record_id"]: row for row in receipts}
    digest_cache: dict[tuple[int, int, int], str] = {}
    checked_hashes = 0
    for row in receipts:
        source = ROOT / Path(row["local_path"])
        require(source.is_file(), f"downloaded video missing: {source}")
        require(source.stat().st_size == int(row["bytes"]), f"video byte count differs: {row['record_id']}")
        if args.verify_hashes:
            identity = file_identity(source)
            digest_cache.setdefault(identity, sha256_file(source))
            require(digest_cache[identity] == row["sha256"], f"raw SHA-256 differs: {row['record_id']}")
            checked_hashes += 1

    for row in bundle_manifest:
        record_id = row["record_id"]
        video = bundle_dir / Path(row["video_path"])
        require(video.is_file(), f"bundle video missing: {record_id}")
        require(row["source_sha256"] == receipt_by_id[record_id]["sha256"], f"bundle manifest hash differs: {record_id}")
        frames = list((bundle_dir / "items" / record_id / "frames").glob("*.jpg"))
        require(len(frames) == 5, f"expected five review frames for {record_id}, found {len(frames)}")
        if args.verify_hashes:
            identity = file_identity(video)
            digest_cache.setdefault(identity, sha256_file(video))
            require(digest_cache[identity] == row["source_sha256"], f"bundle video SHA-256 differs: {record_id}")
            checked_hashes += 1

    require(len(queries) == 100, "paper query set must contain 100 rows")
    require(len({row["query_id"] for row in queries}) == 100, "query_id values must be unique")
    require(len({row["query_text"] for row in queries}) == 100, "query text values must be unique")
    require(Counter(row["language"] for row in queries) == {"zh-CN": 50, "en": 50}, "language distribution differs")
    require(
        Counter(row["split"] for row in queries) == {"development": 60, "source_disjoint_test": 40},
        "query split distribution differs",
    )
    require(
        Counter(row["query_type"] for row in queries)
        == {"operation": 18, "state": 18, "component": 18, "maintenance": 18, "troubleshooting": 16, "safety": 12},
        "query type distribution differs",
    )
    for row in queries:
        detected = detected_products(row["query_text"])
        require(detected == {row["product_class"]}, f"query routing mismatch for {row['query_id']}: {detected}")

    result = {
        "status": "PASS",
        "archive_candidates": len(inventory),
        "technical": dict(technical_counts),
        "ai_content": dict(content_counts),
        "r1_queue": {
            "total": len(queue),
            "scope": dict(scope_counts),
            "priority": dict(priority_counts),
            "full_positive_by_class": dict(positive_class_counts),
        },
        "bundle": {
            "directory": os.fspath(bundle_dir),
            "videos": len(bundle_manifest),
            "frames": len(bundle_manifest) * 5,
            "workbook": os.fspath(workbook),
            "dropdown_rules": validation_rule_count,
        },
        "queries": len(queries),
        "hashes_recomputed": checked_hashes,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
