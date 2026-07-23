#!/usr/bin/env python3
"""Create an auditable processed copy of a completed R1 review CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

from video_rag.manifest_io import ROOT, read_csv, write_csv


LOG_FIELDS = [
    "record_id",
    "field",
    "original_value",
    "normalized_value",
    "normalization_rule",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--log-output",
        type=Path,
        default=ROOT
        / "data_video"
        / "manifests"
        / "r1_expansion_normalization_log_20260723.csv",
    )
    return parser.parse_args()


def derived_rejection_reason(row: dict[str, str]) -> str:
    reasons: list[str] = []
    if row["corrected_product_class"] == "Other":
        reasons.append("corrected_product_class=Other")
    if row["corrected_procedure_relevance"] != "yes":
        reasons.append(
            "corrected_procedure_relevance="
            f"{row['corrected_procedure_relevance']}"
        )
    if row["corrected_functional_step_visible"] != "yes":
        reasons.append(
            "corrected_functional_step_visible="
            f"{row['corrected_functional_step_visible']}"
        )
    if row["license_evidence_status"] != "verified":
        reasons.append(
            f"license_evidence_status={row['license_evidence_status']}"
        )
    if row["privacy_risk"] in {"high", "uncertain"}:
        reasons.append(f"privacy_risk={row['privacy_risk']}")
    if row["safety_risk"] in {"high", "uncertain"}:
        reasons.append(f"safety_risk={row['safety_risk']}")
    if not reasons:
        reasons.append("R1 final_decision=reject")
    return "Derived from completed R1 fields: " + "; ".join(reasons)


def main() -> None:
    args = parse_args()
    rows = read_csv(args.input)
    if len(rows) != 121:
        raise ValueError(f"Expected 121 R1 rows, found {len(rows)}")
    fields = list(rows[0])
    logs: list[dict[str, str]] = []
    for row in rows:
        if (
            row["final_decision"] == "reject"
            and not row["correction_reason"].strip()
        ):
            normalized = derived_rejection_reason(row)
            logs.append(
                {
                    "record_id": row["record_id"],
                    "field": "correction_reason",
                    "original_value": "",
                    "normalized_value": normalized,
                    "normalization_rule": (
                        "Populate required rejection reason only from "
                        "completed R1 categorical fields; raw workbook unchanged."
                    ),
                }
            )
            row["correction_reason"] = normalized
    write_csv(args.output, fields, rows)
    write_csv(args.log_output, LOG_FIELDS, logs)
    print(
        f"rows={len(rows)} normalized_rejection_reasons={len(logs)} "
        f"output={args.output}"
    )


if __name__ == "__main__":
    main()
