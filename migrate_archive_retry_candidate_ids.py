#!/usr/bin/env python3
"""Assign collision-free IDs to newly downloaded legacy Archive seeds."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ID_MAP = {
    "airfryer-001": "airfryer-029",
    "airfryer-003": "airfryer-030",
    "airfryer-007": "airfryer-031",
    "airfryer-009": "airfryer-032",
    "airfryer-012": "airfryer-033",
    "airfryer-013": "airfryer-034",
    "airfryer-014": "airfryer-035",
    "pressure-002": "pressure-032",
    "pressure-003": "pressure-033",
    "pressure-005": "pressure-034",
    "pressure-007": "pressure-035",
    "pressure-008": "pressure-036",
    "pressure-014": "pressure-037",
    "pressure-015": "pressure-038",
    "pressure-018": "pressure-039",
    "pressure-019": "pressure-040",
}

MANIFESTS = (
    ROOT / "data_video" / "manifests" / "archive_candidate_seeds.csv",
    ROOT / "data_video" / "manifests" / "archive_candidates.csv",
    ROOT / "data_video" / "manifests" / "archive_candidate_download_receipts.csv",
    ROOT / "data_video" / "manifests" / "archive_candidate_technical_screen.csv",
    ROOT / "data_video" / "manifests" / "archive_candidate_content_screen.csv",
)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def safe_project_path(value: str) -> Path:
    candidate = (ROOT / value.replace("\\", "/")).resolve()
    candidate.relative_to(ROOT.resolve())
    return candidate


def rewrite_text(value: str, old: str, new: str) -> str:
    return value.replace(old, new)


def main() -> None:
    receipt_path = ROOT / "data_video" / "manifests" / "archive_candidate_download_receipts.csv"
    _, receipt_rows = read_csv(receipt_path)
    receipts = {row["record_id"]: row for row in receipt_rows}

    for old, new in ID_MAP.items():
        receipt = receipts.get(old)
        if receipt:
            source = safe_project_path(receipt["local_path"])
            destination = source.with_name(source.name.replace(old, new, 1))
            if source.is_file():
                if destination.exists():
                    raise FileExistsError(destination)
                source.rename(destination)
                print(f"renamed_media={old}->{new} path={destination.relative_to(ROOT)}")
        frame_source = ROOT / "data_video" / "review" / "archive_candidate_frames" / old
        frame_destination = frame_source.with_name(new)
        if frame_source.is_dir():
            if frame_destination.exists():
                raise FileExistsError(frame_destination)
            frame_source.rename(frame_destination)
            print(f"renamed_frames={old}->{new}")

    for path in MANIFESTS:
        if not path.exists():
            continue
        fields, rows = read_csv(path)
        changed = 0
        for row in rows:
            old = row.get("record_id", "")
            new = ID_MAP.get(old)
            if not new:
                continue
            row["record_id"] = new
            for field, value in list(row.items()):
                if field != "record_id" and isinstance(value, str):
                    row[field] = rewrite_text(value, old, new)
            changed += 1
        if changed:
            ids = [row.get("record_id", "") for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"ID collision after migration in {path}")
            write_csv(path, fields, rows)
        print(f"manifest={path.relative_to(ROOT)} changed={changed}")

    report = {
        "schema_version": "archive-retry-id-migration-v1",
        "mapping": ID_MAP,
        "reason": "legacy Archive seed IDs collided with earlier Wikimedia candidate IDs",
    }
    output = ROOT / "data_video" / "manifests" / "archive_retry_id_migration_20260723.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"report={output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
