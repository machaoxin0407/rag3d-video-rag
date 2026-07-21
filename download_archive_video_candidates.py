#!/usr/bin/env python3
"""Resolve and download owner-authorized Internet Archive video candidates."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parent
INVENTORY_FIELDS = [
    "record_id", "product_class", "title", "source_platform",
    "source_page_url", "creator", "license_id", "license_url",
    "license_evidence_url", "license_checked_at", "duration_seconds",
    "width", "height", "language", "procedure_or_scene", "relevance",
    "commercial_use", "modification", "redistribution_rule",
    "personality_or_privacy", "status", "status_reason", "reviewer_1",
    "reviewer_2", "local_file_sha256", "notes",
]
RECEIPT_FIELDS = [
    "record_id", "inventory_status", "source_page_url", "direct_url",
    "source_variant", "transport", "local_path", "downloaded_at", "bytes",
    "sha256", "content_type", "etag", "last_modified", "authorization_reference",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seeds", type=Path,
        default=ROOT / "data_video" / "manifests" / "archive_candidate_seeds.csv",
    )
    parser.add_argument(
        "--inventory", type=Path,
        default=ROOT / "data_video" / "manifests" / "archive_candidates.csv",
    )
    parser.add_argument(
        "--receipts", type=Path,
        default=ROOT / "data_video" / "manifests" / "archive_candidate_download_receipts.csv",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "data_video" / "raw" / "archive_candidates",
    )
    parser.add_argument("--max-bytes", type=int, default=350_000_000)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument(
        "--transport",
        choices=("requests", "powershell"),
        default="powershell" if sys.platform == "win32" else "requests",
    )
    parser.add_argument(
        "--authorization-reference",
        default="owner-confirmed-2026-07-21-dataset-expansion",
    )
    return parser.parse_args()


def plain(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def request_json(session: requests.Session, url: str) -> dict[str, Any]:
    for attempt in range(5):
        response = session.get(url, timeout=(20, 120))
        if response.status_code not in {429, 502, 503, 504}:
            response.raise_for_status()
            return response.json()
        time.sleep(min(15 * (2**attempt), 180))
    raise RuntimeError(f"Metadata request failed repeatedly: {url}")


def numeric(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def choose_video_file(files: list[dict[str, Any]], max_bytes: int) -> dict[str, Any] | None:
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for item in files:
        name = str(item.get("name", ""))
        lower = name.lower()
        size = numeric(item.get("size"))
        if not lower.endswith((".mp4", ".webm", ".ogv")):
            continue
        if size < 500_000 or size > max_bytes:
            continue
        if any(token in lower for token in ("sample", "trailer", "thumb", "spectrogram")):
            continue
        width = numeric(item.get("width"))
        height = numeric(item.get("height"))
        format_name = str(item.get("format", "")).lower()
        score = 0
        score += 50 if "512kb" in lower else 0
        score += 40 if lower.endswith(".mp4") else 20
        score += 25 if "h.264" in format_name or "mpeg4" in format_name else 0
        score += 20 if 360 <= height <= 720 else 0
        score += min(width // 160, 10)
        candidates.append((score, -size, item))
    if not candidates:
        return None
    return max(candidates, key=lambda value: (value[0], value[1]))[2]


def load_rows(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as stream:
        return {row[key]: row for row in csv.DictReader(stream)}


def write_rows(path: Path, fields: list[str], rows: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))
    os.replace(temporary, path)


def license_fields(metadata: dict[str, Any], authorization: str) -> tuple[str, str, str]:
    url = plain(metadata.get("licenseurl"))
    normalized = url.lower()
    if "creativecommons.org/licenses/by-sa/" in normalized:
        return "CC-BY-SA", url, "share-alike attribution required"
    if "creativecommons.org/licenses/by/" in normalized:
        return "CC-BY", url, "attribution required"
    if "creativecommons.org/publicdomain/zero/" in normalized:
        return "CC0-1.0", url, "redistribution allowed"
    return "OWNER-WRITTEN-AUTHORIZATION", "", f"restricted to authorization {authorization}"


def download(
    session: requests.Session,
    url: str,
    destination: Path,
    max_bytes: int,
    transport: str,
) -> dict[str, str]:
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.unlink(missing_ok=True)
    if transport == "powershell":
        environment = os.environ.copy()
        environment["RAG3D_ARCHIVE_URL"] = url
        environment["RAG3D_ARCHIVE_OUTPUT"] = str(partial.resolve())
        command = (
            "$ProgressPreference='SilentlyContinue'; "
            "$u=[Environment]::GetEnvironmentVariable('RAG3D_ARCHIVE_URL'); "
            "$o=[Environment]::GetEnvironmentVariable('RAG3D_ARCHIVE_OUTPUT'); "
            "Invoke-WebRequest -UseBasicParsing -Uri $u -OutFile $o -TimeoutSec 1800"
        )
        try:
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                check=True,
                env=environment,
            )
            if partial.stat().st_size > max_bytes:
                raise ValueError(f"download exceeds limit {max_bytes}")
            os.replace(partial, destination)
            return {}
        finally:
            partial.unlink(missing_ok=True)

    response = session.get(url, stream=True, timeout=(20, 300))
    response.raise_for_status()
    expected = numeric(response.headers.get("content-length"))
    if expected > max_bytes:
        response.close()
        raise ValueError(f"remote size {expected} exceeds limit {max_bytes}")
    total = 0
    try:
        with partial.open("wb") as stream:
            for block in response.iter_content(1024 * 1024):
                if not block:
                    continue
                total += len(block)
                if total > max_bytes:
                    raise ValueError(f"stream exceeds limit {max_bytes}")
                stream.write(block)
        os.replace(partial, destination)
        headers = {
            "content-type": response.headers.get("content-type", ""),
            "etag": response.headers.get("etag", ""),
            "last-modified": response.headers.get("last-modified", ""),
        }
        response.close()
        return headers
    except Exception:
        response.close()
        partial.unlink(missing_ok=True)
        raise


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    inventory = load_rows(args.inventory, "record_id")
    receipts = load_rows(args.receipts, "record_id")
    with args.seeds.open("r", encoding="utf-8", newline="") as stream:
        seeds = list(csv.DictReader(stream))

    session = requests.Session()
    session.headers["User-Agent"] = "RAG3D-DatasetBuilder/0.2 (academic dataset audit)"
    failures: list[str] = []
    for seed in seeds:
        record_id = seed["record_id"]
        try:
            prior = receipts.get(record_id)
            if prior:
                prior_path = ROOT / prior["local_path"]
                if prior_path.exists() and sha256_file(prior_path) == prior["sha256"]:
                    print(f"skipped_existing={record_id} bytes={prior['bytes']}")
                    continue
            identifier = seed["archive_identifier"]
            metadata_url = f"https://archive.org/metadata/{quote(identifier, safe='')}"
            payload = request_json(session, metadata_url)
            metadata = payload.get("metadata", {})
            selected = choose_video_file(payload.get("files", []), args.max_bytes)
            if selected is None:
                raise ValueError("no bounded downloadable video file")
            filename = str(selected["name"])
            direct_url = (
                f"https://archive.org/download/{quote(identifier, safe='')}/"
                f"{quote(filename, safe='')}"
            )
            suffix = Path(filename).suffix.lower()
            destination = args.output_dir / f"{record_id}{suffix}"
            response_headers = download(
                session, direct_url, destination, args.max_bytes, args.transport
            )
            digest = sha256_file(destination)
            license_id, license_url, redistribution = license_fields(
                metadata, args.authorization_reference
            )
            source_page = f"https://archive.org/details/{quote(identifier, safe='')}"
            inventory[record_id] = {
                "record_id": record_id,
                "product_class": seed["product_class"],
                "title": plain(metadata.get("title")) or identifier,
                "source_platform": "Internet Archive",
                "source_page_url": source_page,
                "creator": plain(metadata.get("creator")) or "Archive contributor",
                "license_id": license_id,
                "license_url": license_url,
                "license_evidence_url": source_page,
                "license_checked_at": datetime.now(timezone.utc).date().isoformat(),
                "duration_seconds": plain(selected.get("length")),
                "width": plain(selected.get("width")),
                "height": plain(selected.get("height")),
                "language": plain(metadata.get("language")) or "und",
                "procedure_or_scene": seed["procedure_or_scene"],
                "relevance": "machine_candidate",
                "commercial_use": "owner_authorized",
                "modification": "owner_authorized",
                "redistribution_rule": redistribution,
                "personality_or_privacy": "pending_content_screen",
                "status": "owner_authorized_candidate",
                "status_reason": "Owner-authorized download; pending automated scope and quality screening",
                "reviewer_1": "Codex-machine-prescreen",
                "reviewer_2": "",
                "local_file_sha256": digest,
                "notes": f"{seed['candidate_split']}; archive_file={filename}",
            }
            receipts[record_id] = {
                "record_id": record_id,
                "inventory_status": "owner_authorized_candidate",
                "source_page_url": source_page,
                "direct_url": direct_url,
                "source_variant": plain(selected.get("format")) or "archive_file",
                "transport": args.transport,
                "local_path": str(destination.relative_to(ROOT)),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "bytes": str(destination.stat().st_size),
                "sha256": digest,
                "content_type": response_headers.get("content-type", "").split(";", 1)[0],
                "etag": response_headers.get("etag", ""),
                "last_modified": response_headers.get("last-modified", ""),
                "authorization_reference": args.authorization_reference,
            }
            write_rows(args.inventory, INVENTORY_FIELDS, inventory)
            write_rows(args.receipts, RECEIPT_FIELDS, receipts)
            print(
                f"downloaded={record_id} bytes={destination.stat().st_size} "
                f"sha256={digest}"
            )
            time.sleep(args.delay_seconds)
        except Exception as exc:
            failures.append(f"{record_id}: {exc}")
            print(f"failed={record_id} error={exc}")

    print(f"selected={len(seeds)} completed={len(receipts)} failures={len(failures)}")
    if failures:
        print("failure_summary=" + " | ".join(failures))


if __name__ == "__main__":
    main()
