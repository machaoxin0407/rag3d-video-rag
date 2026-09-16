#!/usr/bin/env python3
"""Deterministically select the exact R1 expansion needed for six balanced classes."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


TARGET_CLASSES = (
    "Air Fryer",
    "Espresso Machine",
    "Pressure Cooker",
    "Printer",
    "Vacuum",
    "Washing Machine",
)
TARGET_PER_CLASS = 13
AUDIT_FIELDS = (
    "record_id",
    "product_class",
    "selection_status",
    "selection_rank",
    "class_baseline_count",
    "class_target",
    "class_requested_additions",
    "selection_reason",
    "dataset_split",
    "privacy_risk",
    "safety_risk",
    "ai_procedure_relevance",
    "creator",
    "source_page_url",
    "final_decision",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, action="append", required=True)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("data_video/manifests/video_source_inventory.csv"),
    )
    parser.add_argument("--output-selected", type=Path, required=True)
    parser.add_argument("--output-audit", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--target-per-class", type=int, default=TARGET_PER_CLASS)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, fields: list[str] | tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def normalized(value: str) -> str:
    return " ".join(value.casefold().strip().rstrip("/").split())


def eligible(row: dict[str, str]) -> tuple[bool, str]:
    if row.get("final_decision") != "accept":
        return False, "not_accepted_by_r1"
    if row.get("review_status") != "completed":
        return False, "review_incomplete"
    if row.get("license_evidence_status") != "verified":
        return False, "license_not_verified"
    if row.get("corrected_product_class") not in TARGET_CLASSES:
        return False, "outside_target_taxonomy"
    if row.get("corrected_procedure_relevance") != "yes":
        return False, "procedure_not_confirmed"
    if row.get("corrected_functional_step_visible") != "yes":
        return False, "functional_step_not_confirmed"
    if row.get("privacy_risk") not in {"none", "low"}:
        return False, "privacy_gate_failed"
    if row.get("safety_risk") not in {"none", "low"}:
        return False, "safety_gate_failed"
    if row.get("dataset_split") not in {"development", "source_disjoint_test"}:
        return False, "dataset_split_not_frozen"
    return True, ""


def main() -> None:
    args = parse_args()
    if args.target_per_class <= 0:
        raise ValueError("--target-per-class must be positive")

    baseline = read_csv(args.baseline)
    baseline_counts = Counter(
        row["product_class"] for row in baseline if row.get("product_class") in TARGET_CLASSES
    )
    baseline_sources = {
        normalized(row.get("source_page_url", ""))
        for row in baseline
        if normalized(row.get("source_page_url", ""))
    }
    baseline_creators = Counter(
        normalized(row.get("creator", ""))
        for row in baseline
        if normalized(row.get("creator", ""))
    )

    rows: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for path in args.queue:
        for row in read_csv(path):
            record_id = row["record_id"]
            if record_id in seen_ids:
                raise ValueError(f"Duplicate review record: {record_id}")
            seen_ids.add(record_id)
            rows.append(row)
    if not rows:
        raise ValueError("No review rows")
    queue_fields = list(rows[0])

    candidates_by_class: dict[str, list[dict[str, str]]] = defaultdict(list)
    ineligible_reason: dict[str, str] = {}
    for row in rows:
        ok, reason = eligible(row)
        if ok:
            candidates_by_class[row["corrected_product_class"]].append(row)
        else:
            ineligible_reason[row["record_id"]] = reason

    selected: list[dict[str, str]] = []
    selected_ids: set[str] = set()
    selected_sources = set(baseline_sources)
    selected_creators = Counter(baseline_creators)
    selected_procedures: dict[str, Counter[str]] = defaultdict(Counter)
    selection_rank: dict[str, int] = {}
    selection_reason: dict[str, str] = {}
    class_requested: dict[str, int] = {}

    for product_class in TARGET_CLASSES:
        requested = max(args.target_per_class - baseline_counts[product_class], 0)
        class_requested[product_class] = requested
        pool = list(candidates_by_class[product_class])
        for rank in range(1, requested + 1):
            available = [
                row
                for row in pool
                if row["record_id"] not in selected_ids
                and (
                    not normalized(row.get("source_page_url", ""))
                    or normalized(row.get("source_page_url", "")) not in selected_sources
                )
            ]
            if not available:
                break

            def priority(row: dict[str, str]) -> tuple[object, ...]:
                procedure = row.get("ai_procedure_relevance", "") or "unspecified"
                creator = normalized(row.get("creator", ""))
                correction_count = sum(
                    (
                        row.get("ai_expected_product_class") != row.get("corrected_product_class"),
                        row.get("ai_functional_step_visible") != "yes",
                        row.get("ai_procedure_relevance") in {"irrelevant", "promotion", "uncertain"},
                    )
                )
                return (
                    0 if row.get("dataset_split") == "source_disjoint_test" else 1,
                    0 if row.get("privacy_risk") == "none" else 1,
                    0 if row.get("safety_risk") == "none" else 1,
                    selected_procedures[product_class][procedure],
                    selected_creators[creator] if creator else 999,
                    correction_count,
                    row["record_id"],
                )

            chosen = min(available, key=priority)
            selected.append(chosen)
            selected_ids.add(chosen["record_id"])
            source = normalized(chosen.get("source_page_url", ""))
            creator = normalized(chosen.get("creator", ""))
            procedure = chosen.get("ai_procedure_relevance", "") or "unspecified"
            if source:
                selected_sources.add(source)
            if creator:
                selected_creators[creator] += 1
            selected_procedures[product_class][procedure] += 1
            selection_rank[chosen["record_id"]] = rank
            selection_reason[chosen["record_id"]] = (
                f"selected_for_class_balance; split={chosen['dataset_split']}; "
                f"privacy={chosen['privacy_risk']}; safety={chosen['safety_risk']}; "
                f"procedure={procedure}; deterministic_rank={rank}"
            )

    selected.sort(key=lambda row: (TARGET_CLASSES.index(row["corrected_product_class"]), row["record_id"]))
    write_csv(args.output_selected, queue_fields, selected)

    audit_rows: list[dict[str, str]] = []
    for row in sorted(rows, key=lambda item: item["record_id"]):
        record_id = row["record_id"]
        product_class = row.get("corrected_product_class") or row.get("ai_expected_product_class", "")
        if record_id in selected_ids:
            status = "selected"
            reason = selection_reason[record_id]
        elif record_id in ineligible_reason:
            status = "not_eligible"
            reason = ineligible_reason[record_id]
        elif normalized(row.get("source_page_url", "")) in baseline_sources:
            status = "reserve"
            reason = "duplicate_source_with_baseline"
        else:
            status = "reserve"
            reason = "eligible_reserve_after_class_quota"
        audit_rows.append(
            {
                "record_id": record_id,
                "product_class": product_class,
                "selection_status": status,
                "selection_rank": str(selection_rank.get(record_id, "")),
                "class_baseline_count": str(baseline_counts.get(product_class, 0)),
                "class_target": str(args.target_per_class),
                "class_requested_additions": str(class_requested.get(product_class, 0)),
                "selection_reason": reason,
                "dataset_split": row.get("dataset_split", ""),
                "privacy_risk": row.get("privacy_risk", ""),
                "safety_risk": row.get("safety_risk", ""),
                "ai_procedure_relevance": row.get("ai_procedure_relevance", ""),
                "creator": row.get("creator", ""),
                "source_page_url": row.get("source_page_url", ""),
                "final_decision": row.get("final_decision", ""),
            }
        )
    write_csv(args.output_audit, AUDIT_FIELDS, audit_rows)

    selected_counts = Counter(row["corrected_product_class"] for row in selected)
    final_counts = {
        product_class: baseline_counts[product_class] + selected_counts[product_class]
        for product_class in TARGET_CLASSES
    }
    remaining_gaps = {
        product_class: max(args.target_per_class - final_counts[product_class], 0)
        for product_class in TARGET_CLASSES
    }
    summary = {
        "selection_protocol": "r1_exact_class_balance_diversity_v1",
        "baseline_policy": "all existing six-class inventory records; legacy review status preserved",
        "target_per_class": args.target_per_class,
        "baseline_counts": dict(baseline_counts),
        "requested_additions": class_requested,
        "eligible_counts": {
            product_class: len(candidates_by_class[product_class])
            for product_class in TARGET_CLASSES
        },
        "selected_counts": {
            product_class: selected_counts[product_class]
            for product_class in TARGET_CLASSES
        },
        "final_counts_before_pending_gap_review": final_counts,
        "remaining_gaps": remaining_gaps,
        "selected_total": len(selected),
        "reserve_total": sum(row["selection_status"] == "reserve" for row in audit_rows),
        "not_eligible_total": sum(row["selection_status"] == "not_eligible" for row in audit_rows),
    }
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
