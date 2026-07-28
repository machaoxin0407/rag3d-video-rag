#!/usr/bin/env python3
"""Freeze the adjudicated paper relevance workbook into auditable qrels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "paper-video-qrels-v1"
PRIMARY_BINARY_THRESHOLD = 2
AUDIT_FIELDS = [
    "query_id",
    "query_text",
    "language",
    "product_class",
    "query_type",
    "split",
    "candidate_scene_id",
    "record_id",
    "scene_start_time",
    "scene_end_time",
    "relevance_grade",
    "relevant_start_time",
    "relevant_end_time",
    "source_leakage",
    "evidence_notes",
    "correction_reason",
    "reviewer_id",
    "review_status",
    "reviewed_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--crosscheck-report", type=Path, required=True)
    parser.add_argument("--progress-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def as_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalized_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def times_changed(row: dict[str, Any]) -> bool:
    human_start = as_number(row["r1_start_time"])
    human_end = as_number(row["r1_end_time"])
    ai_start = as_number(row["ai_start_time"])
    ai_end = as_number(row["ai_end_time"])
    return (human_start, human_end) != (ai_start, ai_end)


def validate_row(row: dict[str, Any], row_number: int) -> dict[str, Any]:
    prefix = f"Workbook row {row_number}"
    grade = as_number(row["r1_relevance_grade"])
    if grade is None or int(grade) != grade or int(grade) not in range(4):
        raise ValueError(f"{prefix}: invalid relevance grade")
    grade_int = int(grade)
    if normalized_text(row["review_status"]) != "completed":
        raise ValueError(f"{prefix}: review_status is not completed")
    leakage = normalized_text(row["r1_source_leakage"])
    if leakage not in {"no", "yes", "uncertain"}:
        raise ValueError(f"{prefix}: invalid source leakage")
    if not normalized_text(row["r1_evidence_notes"]):
        raise ValueError(f"{prefix}: evidence notes are blank")
    if not normalized_text(row["reviewed_at"]):
        raise ValueError(f"{prefix}: reviewed_at is blank")

    scene_start = as_number(row["scene_start_time"])
    scene_end = as_number(row["scene_end_time"])
    human_start = as_number(row["r1_start_time"])
    human_end = as_number(row["r1_end_time"])
    if scene_start is None or scene_end is None or scene_end <= scene_start:
        raise ValueError(f"{prefix}: invalid scene interval")
    if grade_int <= 1:
        if human_start is not None or human_end is not None:
            raise ValueError(f"{prefix}: grade 0/1 must have blank relevance times")
    elif (
        human_start is None
        or human_end is None
        or human_start < scene_start
        or human_end > scene_end
        or human_end <= human_start
    ):
        raise ValueError(f"{prefix}: grade 2/3 has an invalid relevance interval")

    ai_grade = as_number(row["ai_relevance_grade"])
    changed = ai_grade is None or int(ai_grade) != grade_int or times_changed(row)
    if changed and not normalized_text(row["correction_reason"]):
        raise ValueError(f"{prefix}: changed judgment lacks correction_reason")

    return {
        "query_id": normalized_text(row["query_id"]),
        "query_text": normalized_text(row["query_text"]),
        "language": normalized_text(row["language"]),
        "product_class": normalized_text(row["product_class"]),
        "query_type": normalized_text(row["query_type"]),
        "split": normalized_text(row["split"]),
        "candidate_scene_id": normalized_text(row["candidate_scene_id"]),
        "record_id": normalized_text(row["record_id"]),
        "scene_start_time": round(scene_start, 3),
        "scene_end_time": round(scene_end, 3),
        "relevance_grade": grade_int,
        "relevant_start_time": "" if human_start is None else round(human_start, 3),
        "relevant_end_time": "" if human_end is None else round(human_end, 3),
        "source_leakage": leakage,
        "evidence_notes": normalized_text(row["r1_evidence_notes"]),
        "correction_reason": normalized_text(row["correction_reason"]),
        "reviewer_id": normalized_text(row["reviewer_id"]),
        "review_status": "completed",
        "reviewed_at": normalized_text(row["reviewed_at"]),
    }


def load_rows(workbook_path: Path) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise SystemExit("openpyxl is required to read the frozen review workbook") from exc

    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    raw_headers = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
    headers = [
        normalized_text(value).lstrip("\ufeff") for value in raw_headers
    ]
    required = {
        "query_id", "query_text", "language", "product_class", "query_type",
        "split", "candidate_scene_id", "record_id", "scene_start_time",
        "scene_end_time", "ai_relevance_grade", "ai_start_time", "ai_end_time",
        "reviewer_id", "r1_relevance_grade", "r1_start_time", "r1_end_time",
        "r1_source_leakage", "r1_evidence_notes", "correction_reason",
        "review_status", "reviewed_at",
    }
    missing = sorted(required - set(headers))
    if missing:
        raise ValueError(f"Workbook is missing columns: {missing}")
    result: list[dict[str, Any]] = []
    for row_number, values in enumerate(
        sheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        row = {header: values[index] for index, header in enumerate(headers)}
        result.append(validate_row(row, row_number))
    return result


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=AUDIT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    sources = [args.workbook, args.crosscheck_report, args.progress_report]
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "audit_csv": output_dir / "paper_video_qrels_graded_v1.csv",
        "trec_graded": output_dir / "paper_video_qrels_graded_v1.txt",
        "trec_binary": output_dir / "paper_video_qrels_binary_ge2_v1.txt",
        "manifest": output_dir / "paper_video_qrels_manifest_v1.json",
    }
    existing = [path for path in outputs.values() if path.exists()]
    if existing and not args.force:
        raise FileExistsError(f"Refusing to replace frozen qrels: {existing}")

    rows = load_rows(args.workbook)
    pairs = [(row["query_id"], row["candidate_scene_id"]) for row in rows]
    if len(rows) != 3775:
        raise ValueError(f"Expected 3775 judgments, found {len(rows)}")
    if len(set(pairs)) != len(pairs):
        raise ValueError("Duplicate query-scene pairs in final workbook")
    queries = {row["query_id"] for row in rows}
    scenes = {row["candidate_scene_id"] for row in rows}
    if len(queries) != 100 or len(scenes) != 725:
        raise ValueError(
            f"Unexpected coverage: queries={len(queries)} scenes={len(scenes)}"
        )

    rows.sort(key=lambda row: (row["query_id"], row["candidate_scene_id"]))
    write_csv(outputs["audit_csv"], rows)
    with outputs["trec_graded"].open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                f"{row['query_id']} 0 {row['candidate_scene_id']} "
                f"{row['relevance_grade']}\n"
            )
    with outputs["trec_binary"].open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            relevant = int(row["relevance_grade"] >= PRIMARY_BINARY_THRESHOLD)
            stream.write(
                f"{row['query_id']} 0 {row['candidate_scene_id']} {relevant}\n"
            )

    grade_counts = Counter(str(row["relevance_grade"]) for row in rows)
    leakage_counts = Counter(row["source_leakage"] for row in rows)
    positive_queries = {
        row["query_id"]
        for row in rows
        if row["relevance_grade"] >= PRIMARY_BINARY_THRESHOLD
    }
    graded_positive_queries = {
        row["query_id"] for row in rows if row["relevance_grade"] >= 1
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frozen": True,
        "judgment_scope": {
            "queries": len(queries),
            "query_scene_pairs": len(rows),
            "unique_scenes": len(scenes),
            "grade_counts": dict(sorted(grade_counts.items())),
            "source_leakage_counts": dict(sorted(leakage_counts.items())),
            "queries_with_grade_ge_1": len(graded_positive_queries),
            "queries_with_grade_ge_2": len(positive_queries),
        },
        "primary_binary_relevance": "relevance_grade >= 2",
        "graded_gain": "2^relevance_grade - 1",
        "human_review_protocol": {
            "minimum_independent_human_reviewers_per_row": 2,
            "disputed_rows_receive_third_human_adjudication": True,
            "full_crosscheck_rows": 3775,
            "full_crosscheck_agreement": 0.951,
            "high_grade_deep_review_rows": 245,
            "third_party_adjudication_rows": 146,
            "applied_r3_corrections": 142,
        },
        "source_files": {
            "workbook": {
                "name": args.workbook.name,
                "sha256": sha256_file(args.workbook),
            },
            "crosscheck_report": {
                "name": args.crosscheck_report.name,
                "sha256": sha256_file(args.crosscheck_report),
            },
            "progress_report": {
                "name": args.progress_report.name,
                "sha256": sha256_file(args.progress_report),
            },
        },
        "outputs": {
            key: {
                "name": path.name,
                "sha256": sha256_file(path),
            }
            for key, path in outputs.items()
            if key != "manifest"
        },
    }
    outputs["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"paper_video_qrels_freeze={output_dir}")


if __name__ == "__main__":
    main()
