#!/usr/bin/env python3
"""Build the single-reviewer gate for AI-annotated video candidates."""

from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


FIELDS = [
    "record_id",
    "review_scope",
    "ai_expected_product_class",
    "ai_predicted_product_class",
    "title",
    "source_platform",
    "source_page_url",
    "creator",
    "license_id",
    "candidate_split",
    "technical_decision",
    "ai_decision",
    "ai_procedure_relevance",
    "ai_functional_step_visible",
    "ai_visual_evidence",
    "ai_uncertainty",
    "sample_frame_paths",
    "review_priority",
    "prescreen_flags",
    "reviewer_id",
    "review_status",
    "license_evidence_status",
    "corrected_product_class",
    "corrected_procedure_relevance",
    "corrected_functional_step_visible",
    "privacy_risk",
    "safety_risk",
    "correction_reason",
    "final_decision",
    "dataset_split",
    "reviewed_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-screen", type=Path, action="append", required=True)
    parser.add_argument("--technical-screen", type=Path, action="append", required=True)
    parser.add_argument("--inventory", type=Path, action="append", required=True)
    parser.add_argument("--reject-audit-rate", type=float, default=0.20)
    parser.add_argument("--sample-seed", default="candidate-reject-audit-v1")
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


def stable_rank(record_id: str, seed: str) -> str:
    return hashlib.sha256(f"{seed}:{record_id}".encode()).hexdigest()


def rejected_audit_sample(
    rejected: list[dict[str, str]], rate: float, seed: str
) -> list[dict[str, str]]:
    if not 0 <= rate <= 1:
        raise ValueError("--reject-audit-rate must be between zero and one")
    if not rejected or rate == 0:
        return []
    target = math.ceil(len(rejected) * rate)
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rejected:
        groups.setdefault(row["expected_product_class"], []).append(row)
    target = max(target, len(groups))
    selected: dict[str, dict[str, str]] = {}
    for product_class in sorted(groups):
        first = min(
            groups[product_class],
            key=lambda row: stable_rank(row["record_id"], seed),
        )
        selected[first["record_id"]] = first
    remaining = sorted(
        (row for row in rejected if row["record_id"] not in selected),
        key=lambda row: stable_rank(row["record_id"], seed),
    )
    for row in remaining[: max(target - len(selected), 0)]:
        selected[row["record_id"]] = row
    return list(selected.values())


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
    rejected = [
        row for row in content.values() if row["machine_decision"] == "reject_out_of_scope"
    ]
    audit_sample = rejected_audit_sample(
        rejected, args.reject_audit_rate, args.sample_seed
    )
    queue: list[dict[str, str]] = []
    scoped_rows = [
        ("full_positive_review", row) for row in retained
    ] + [("rejected_audit_sample", row) for row in audit_sample]
    for review_scope, row in scoped_rows:
        record_id = row["record_id"]
        if record_id not in technical or record_id not in inventory:
            raise ValueError(f"Candidate lacks technical or inventory row: {record_id}")
        technical_row = technical[record_id]
        inventory_row = inventory[record_id]
        flags = prescreen_flags(row)
        if review_scope == "rejected_audit_sample":
            flags.append("sampled_ai_rejection")
        if review_scope == "rejected_audit_sample":
            priority = "audit"
        else:
            priority = "high" if flags else "normal"
        queue.append(
            {
                "record_id": record_id,
                "review_scope": review_scope,
                "ai_expected_product_class": row["expected_product_class"],
                "ai_predicted_product_class": row["predicted_product_class"],
                "title": row["title"],
                "source_platform": inventory_row.get("source_platform", ""),
                "source_page_url": inventory_row.get("source_page_url", ""),
                "creator": inventory_row.get("creator", ""),
                "license_id": inventory_row.get("license_id", ""),
                "candidate_split": split_value(inventory_row, technical_row),
                "technical_decision": technical_row["technical_decision"],
                "ai_decision": row["machine_decision"],
                "ai_procedure_relevance": row["procedure_relevance"],
                "ai_functional_step_visible": row["functional_step_visible"],
                "ai_visual_evidence": row["visual_evidence"],
                "ai_uncertainty": row["uncertainty"],
                "sample_frame_paths": technical_row["sample_frame_paths"],
                "review_priority": priority,
                "prescreen_flags": "|".join(flags),
                "reviewer_id": "R1",
                "review_status": "pending",
                "license_evidence_status": "pending",
                "corrected_product_class": "",
                "corrected_procedure_relevance": "",
                "corrected_functional_step_visible": "",
                "privacy_risk": "",
                "safety_risk": "",
                "correction_reason": "",
                "final_decision": "pending",
                "dataset_split": "pending",
                "reviewed_at": "",
            }
        )
    priority_order = {"high": 0, "normal": 1, "audit": 2}
    queue.sort(
        key=lambda row: (
            priority_order[row["review_priority"]],
            row["ai_expected_product_class"],
            row["record_id"],
        )
    )
    write_csv(args.output, FIELDS, queue)
    high = sum(row["review_priority"] == "high" for row in queue)
    print(
        f"review_queue={len(queue)} positives={len(retained)} "
        f"rejected_audit={len(audit_sample)}/{len(rejected)} high_priority={high}"
    )


if __name__ == "__main__":
    main()
