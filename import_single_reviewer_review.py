#!/usr/bin/env python3
"""Validate R1 review rows and merge them into the canonical candidate queue."""

from __future__ import annotations

import argparse
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


IMMUTABLE_FIELDS = [
    "record_id",
    "review_scope",
    "review_priority",
    "ai_expected_product_class",
    "ai_predicted_product_class",
    "title",
    "source_page_url",
    "creator",
    "license_id",
    "candidate_split",
    "ai_decision",
    "ai_procedure_relevance",
    "ai_functional_step_visible",
    "ai_visual_evidence",
    "ai_uncertainty",
    "prescreen_flags",
    "reviewer_id",
]
REVIEW_FIELDS = [
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
TARGET_PRODUCT_CLASSES = {
    "Air Fryer",
    "Espresso Machine",
    "Pressure Cooker",
    "Printer",
    "Vacuum",
    "Washing Machine",
}
ALLOWED_VALUES = {
    "review_status": {"pending", "in_progress", "completed"},
    "license_evidence_status": {"pending", "verified", "failed", "unclear"},
    "corrected_procedure_relevance": {"yes", "no", "uncertain"},
    "corrected_functional_step_visible": {"yes", "no", "uncertain"},
    "privacy_risk": {"none", "low", "high", "uncertain"},
    "safety_risk": {"none", "low", "high", "uncertain"},
    "final_decision": {"pending", "accept", "reject", "hold"},
    "dataset_split": {
        "pending",
        "development",
        "source_disjoint_test",
        "excluded",
    },
}
AI_PROCEDURE_TO_BINARY = {
    "operation": "yes",
    "setup": "yes",
    "maintenance": "yes",
    "troubleshooting": "yes",
    "component_overview": "no",
    "promotion": "no",
    "irrelevant": "no",
    "uncertain": "uncertain",
}
SUMMARY_FIELDS = ["metric", "value", "denominator", "rate", "notes"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-csv", type=Path, required=True)
    parser.add_argument(
        "--canonical-queue",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_review_queue.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "candidate_review_queue.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=ROOT
        / "data_video"
        / "manifests"
        / "single_reviewer_audit_summary.csv",
    )
    parser.add_argument(
        "--split-overrides",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "review_split_overrides.csv",
    )
    return parser.parse_args()


def index_unique(rows: list[dict[str, str]], source: str) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        record_id = row.get("record_id", "")
        if not record_id:
            raise ValueError(f"{source} contains a blank record_id")
        if record_id in indexed:
            raise ValueError(f"{source} contains duplicate record_id: {record_id}")
        indexed[record_id] = row
    return indexed


def validate_iso_date(value: str, record_id: str) -> None:
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{record_id}: reviewed_at is not ISO-8601: {value}") from exc


def validate_row(row: dict[str, str]) -> None:
    record_id = row["record_id"]
    for field, allowed in ALLOWED_VALUES.items():
        if row.get(field, "") not in allowed:
            raise ValueError(f"{record_id}: invalid {field}={row.get(field, '')}")
    if row["review_status"] != "completed":
        raise ValueError(f"{record_id}: review is not completed")
    if row["reviewer_id"] != "R1":
        raise ValueError(f"{record_id}: unexpected reviewer_id={row['reviewer_id']}")
    if not row.get("corrected_product_class"):
        raise ValueError(f"{record_id}: corrected_product_class is blank")
    if not row.get("reviewed_at"):
        raise ValueError(f"{record_id}: reviewed_at is blank")
    validate_iso_date(row["reviewed_at"], record_id)

    decision = row["final_decision"]
    if decision == "accept":
        if row["license_evidence_status"] != "verified":
            raise ValueError(f"{record_id}: accepted row lacks verified license evidence")
        if row["corrected_product_class"] not in TARGET_PRODUCT_CLASSES:
            raise ValueError(f"{record_id}: accepted row has an out-of-scope product class")
        if row["corrected_procedure_relevance"] != "yes":
            raise ValueError(f"{record_id}: accepted row is not procedure relevant")
        if row["corrected_functional_step_visible"] != "yes":
            raise ValueError(f"{record_id}: accepted row lacks a visible functional step")
        if row["privacy_risk"] in {"high", "uncertain"}:
            raise ValueError(f"{record_id}: accepted row has unresolved privacy risk")
        if row["safety_risk"] in {"high", "uncertain"}:
            raise ValueError(f"{record_id}: accepted row has unresolved safety risk")
        if row["dataset_split"] not in {"development", "source_disjoint_test"}:
            raise ValueError(f"{record_id}: accepted row has invalid dataset_split")
    elif decision == "reject":
        if row["dataset_split"] != "excluded":
            raise ValueError(f"{record_id}: rejected row must use dataset_split=excluded")
        if not row.get("correction_reason", "").strip():
            raise ValueError(f"{record_id}: rejected row lacks correction_reason")
    elif decision == "hold":
        if not row.get("correction_reason", "").strip():
            raise ValueError(f"{record_id}: held row lacks correction_reason")
    else:
        raise ValueError(f"{record_id}: final_decision is still pending")


def apply_split_overrides(
    rows: list[dict[str, str]], path: Path
) -> list[dict[str, str]]:
    if not path.exists():
        return [dict(row) for row in rows]
    overrides = index_unique(read_csv(path), "split overrides")
    known_ids = {row["record_id"] for row in rows}
    unknown = sorted(set(overrides) - known_ids)
    if unknown:
        raise ValueError(f"Split overrides contain unknown IDs: {unknown}")
    normalized: list[dict[str, str]] = []
    for source_row in rows:
        row = dict(source_row)
        override = overrides.get(row["record_id"])
        if override:
            if row["dataset_split"] != override["original_split"]:
                raise ValueError(
                    f"{row['record_id']}: split override expected "
                    f"{override['original_split']} but found {row['dataset_split']}"
                )
            row["dataset_split"] = override["normalized_split"]
        normalized.append(row)
    return normalized


def validate_source_disjointness(rows: list[dict[str, str]]) -> None:
    creator_splits: dict[str, set[str]] = {}
    creator_records: dict[str, list[str]] = {}
    for row in rows:
        if row["final_decision"] != "accept":
            continue
        creator = " ".join(row.get("creator", "").lower().split())
        if not creator:
            continue
        creator_splits.setdefault(creator, set()).add(row["dataset_split"])
        creator_records.setdefault(creator, []).append(row["record_id"])
    conflicts = {
        creator: creator_records[creator]
        for creator, splits in creator_splits.items()
        if len(splits) > 1
    }
    if conflicts:
        raise ValueError(f"Accepted records leak creators across splits: {conflicts}")


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def summary_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    positives = [row for row in rows if row["review_scope"] == "full_positive_review"]
    labeled_procedure_positives = [
        row
        for row in positives
        if row["ai_procedure_relevance"] in AI_PROCEDURE_TO_BINARY
    ]
    labeled_step_positives = [
        row
        for row in positives
        if row["ai_functional_step_visible"] in {"yes", "no", "uncertain"}
    ]
    labeled_class_positives = [
        row for row in positives if row["ai_predicted_product_class"]
    ]
    audits = [row for row in rows if row["review_scope"] == "rejected_audit_sample"]
    accepted = [row for row in rows if row["final_decision"] == "accept"]
    rejected = [row for row in rows if row["final_decision"] == "reject"]
    false_rejects = sum(row["final_decision"] == "accept" for row in audits)
    low, high = wilson_interval(false_rejects, len(audits))
    procedure_corrections = 0
    for row in labeled_procedure_positives:
        ai_procedure = row["ai_procedure_relevance"]
        procedure_corrections += (
            AI_PROCEDURE_TO_BINARY[ai_procedure]
            != row["corrected_procedure_relevance"]
        )
    step_corrections = sum(
        row["ai_functional_step_visible"]
        != row["corrected_functional_step_visible"]
        for row in labeled_step_positives
    )
    corrected_class = sum(
        row["ai_predicted_product_class"] != row["corrected_product_class"]
        for row in labeled_class_positives
    )
    class_counts = Counter(row["corrected_product_class"] for row in accepted)

    def metric(
        name: str,
        value: int,
        denominator: int = 0,
        notes: str = "",
    ) -> dict[str, str]:
        return {
            "metric": name,
            "value": str(value),
            "denominator": str(denominator) if denominator else "",
            "rate": f"{value / denominator:.6f}" if denominator else "",
            "notes": notes,
        }

    result = [
        metric("reviewed_total", len(rows)),
        metric("final_accept", len(accepted), len(rows)),
        metric("final_reject", len(rejected), len(rows)),
        metric(
            "accepted_split::development",
            sum(row["dataset_split"] == "development" for row in accepted),
        ),
        metric(
            "accepted_split::source_disjoint_test",
            sum(row["dataset_split"] == "source_disjoint_test" for row in accepted),
        ),
        metric("ai_retained_final_accept", sum(r["final_decision"] == "accept" for r in positives), len(positives)),
        metric("ai_retained_final_reject", sum(r["final_decision"] == "reject" for r in positives), len(positives)),
        metric(
            "ai_retained_product_class_corrections",
            corrected_class,
            len(labeled_class_positives),
        ),
        metric(
            "ai_retained_procedure_corrections",
            procedure_corrections,
            len(labeled_procedure_positives),
        ),
        metric(
            "ai_retained_functional_step_corrections",
            step_corrections,
            len(labeled_step_positives),
        ),
        metric(
            "ai_manual_review_without_complete_labels",
            len(positives) - len(labeled_procedure_positives),
            len(positives),
        ),
        metric(
            "reject_audit_false_rejects",
            false_rejects,
            len(audits),
            f"Wilson 95% CI [{low:.6f}, {high:.6f}]",
        ),
    ]
    for product_class in sorted(TARGET_PRODUCT_CLASSES):
        result.append(metric(f"accepted_class::{product_class}", class_counts[product_class]))
    return result


def main() -> None:
    args = parse_args()
    canonical_rows = read_csv(args.canonical_queue)
    original_review_rows = read_csv(args.review_csv)
    review_rows = apply_split_overrides(original_review_rows, args.split_overrides)
    canonical = index_unique(canonical_rows, "canonical queue")
    reviews = index_unique(review_rows, "review CSV")
    if set(canonical) != set(reviews):
        missing = sorted(set(canonical) - set(reviews))
        extra = sorted(set(reviews) - set(canonical))
        raise ValueError(f"Review IDs differ from queue: missing={missing} extra={extra}")

    merged: list[dict[str, str]] = []
    for canonical_row in canonical_rows:
        record_id = canonical_row["record_id"]
        review_row = reviews[record_id]
        for field in IMMUTABLE_FIELDS:
            if canonical_row.get(field, "") != review_row.get(field, ""):
                raise ValueError(f"{record_id}: immutable field changed: {field}")
        validate_row(review_row)
        merged_row = dict(canonical_row)
        for field in REVIEW_FIELDS:
            merged_row[field] = review_row[field]
        merged.append(merged_row)

    validate_source_disjointness(review_rows)

    fields = list(canonical_rows[0])
    write_csv(args.output, fields, merged)
    summaries = summary_rows(review_rows)
    write_csv(args.summary_output, SUMMARY_FIELDS, summaries)
    decisions = Counter(row["final_decision"] for row in review_rows)
    print(
        f"validated={len(review_rows)} accept={decisions['accept']} "
        f"reject={decisions['reject']} hold={decisions['hold']}"
    )


if __name__ == "__main__":
    main()
