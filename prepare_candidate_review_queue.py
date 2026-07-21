#!/usr/bin/env python3
"""Build the A/B/C human gate for machine-retained video candidates."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


FIELDS = [
    "record_id",
    "product_class",
    "title",
    "source_platform",
    "source_page_url",
    "creator",
    "license_id",
    "candidate_split",
    "technical_decision",
    "machine_decision",
    "machine_visual_evidence",
    "machine_uncertainty",
    "sample_frame_paths",
    "review_priority",
    "prescreen_flags",
    "license_reviewer",
    "license_review_status",
    "license_review_notes",
    "content_reviewer",
    "content_review_status",
    "content_review_notes",
    "adjudicator",
    "adjudication_status",
    "adjudication_notes",
    "final_decision",
    "dataset_split",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-screen", type=Path, action="append", required=True)
    parser.add_argument("--technical-screen", type=Path, action="append", required=True)
    parser.add_argument("--inventory", type=Path, action="append", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_review_queue.csv",
    )
    return parser.parse_args()


def index_rows(paths: list[Path], source: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in paths:
        for row in read_csv(path):
            record_id = row["record_id"]
            if record_id in result:
                raise ValueError(f"Duplicate {source} record: {record_id}")
            result[record_id] = row
    return result


def split_value(inventory: dict[str, str], technical: dict[str, str]) -> str:
    if technical.get("candidate_split"):
        return technical["candidate_split"]
    notes = inventory.get("notes", "")
    if "source_disjoint_test_candidate" in notes:
        return "source_disjoint_test_candidate"
    if "development_candidate" in notes:
        return "development_candidate"
    return "unassigned_candidate"


def prescreen_flags(content: dict[str, str]) -> list[str]:
    flags: list[str] = []
    expected = content["expected_product_class"]
    predicted = content["predicted_product_class"]
    title = content["title"].lower()
    if predicted != expected:
        flags.append("predicted_class_mismatch")
    if content["functional_step_visible"] != "yes":
        flags.append("no_visible_functional_step")
    if expected == "Pressure Cooker" and any(
        token in title for token in ("alcohol", "modification")
    ):
        flags.append("unsafe_or_off_domain_modification")
    if expected == "Vacuum" and any(
        token in title for token in ("packaging", "sealer", "vacuum test", "hoover dam")
    ):
        flags.append("vacuum_wrong_domain_risk")
    if expected == "Printer" and "3-d" in title:
        flags.append("3d_printer_excluded")
    if expected == "Espresso Machine" and any(
        token in title for token in ("moccamaster", "bean that could save")
    ):
        flags.append("espresso_scope_risk")
    return flags


def main() -> None:
    args = parse_args()
    content = index_rows(args.content_screen, "content-screen")
    technical = index_rows(args.technical_screen, "technical-screen")
    inventory = index_rows(args.inventory, "inventory")
    retained = [
        row
        for row in content.values()
        if row["machine_decision"] in {"retain_for_human_review", "manual_review"}
    ]
    queue: list[dict[str, str]] = []
    for row in retained:
        record_id = row["record_id"]
        if record_id not in technical or record_id not in inventory:
            raise ValueError(f"Candidate lacks technical or inventory row: {record_id}")
        technical_row = technical[record_id]
        inventory_row = inventory[record_id]
        flags = prescreen_flags(row)
        queue.append(
            {
                "record_id": record_id,
                "product_class": row["expected_product_class"],
                "title": row["title"],
                "source_platform": inventory_row.get("source_platform", ""),
                "source_page_url": inventory_row.get("source_page_url", ""),
                "creator": inventory_row.get("creator", ""),
                "license_id": inventory_row.get("license_id", ""),
                "candidate_split": split_value(inventory_row, technical_row),
                "technical_decision": technical_row["technical_decision"],
                "machine_decision": row["machine_decision"],
                "machine_visual_evidence": row["visual_evidence"],
                "machine_uncertainty": row["uncertainty"],
                "sample_frame_paths": technical_row["sample_frame_paths"],
                "review_priority": "high" if flags else "normal",
                "prescreen_flags": "|".join(flags),
                "license_reviewer": "A",
                "license_review_status": "pending",
                "license_review_notes": "",
                "content_reviewer": "B",
                "content_review_status": "pending",
                "content_review_notes": "",
                "adjudicator": "C",
                "adjudication_status": "pending",
                "adjudication_notes": "",
                "final_decision": "pending",
                "dataset_split": "pending",
            }
        )
    queue.sort(
        key=lambda row: (
            row["review_priority"] != "high",
            row["product_class"],
            row["record_id"],
        )
    )
    write_csv(args.output, FIELDS, queue)
    high = sum(row["review_priority"] == "high" for row in queue)
    print(f"review_queue={len(queue)} high_priority={high}")


if __name__ == "__main__":
    main()
