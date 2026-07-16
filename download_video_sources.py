#!/usr/bin/env python3
"""Download approved Wikimedia source videos and write auditable receipts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests


ROOT = Path(__file__).resolve().parent
DEFAULT_INVENTORY = ROOT / "data_video" / "manifests" / "video_source_inventory.csv"
DEFAULT_OUTPUT = ROOT / "data_video" / "raw" / "authorized_sources"
DEFAULT_RECEIPTS = ROOT / "data_video" / "manifests" / "download_receipts.csv"
RECEIPT_FIELDS = [
    "record_id",
    "inventory_status",
    "source_page_url",
    "direct_url",
    "local_path",
    "downloaded_at",
    "bytes",
    "sha256",
    "content_type",
    "etag",
    "last_modified",
    "authorization_reference",
]


def parse_args() -> argparse.Namespace:
    """Parse download paths, authorization reference, and safety limits."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipts", type=Path, default=DEFAULT_RECEIPTS)
    parser.add_argument(
        "--statuses",
        default="provisional_accept,scope_review,hold_privacy",
        help="Comma-separated inventory statuses allowed for download.",
    )
    parser.add_argument("--authorization-reference", required=True)
    parser.add_argument("--max-bytes", type=int, default=1_000_000_000)
    parser.add_argument("--delay-seconds", type=float, default=30.0)
    parser.add_argument("--retry-attempts", type=int, default=5)
    parser.add_argument("--retry-base-seconds", type=float, default=30.0)
    return parser.parse_args()


def wikimedia_filename(source_page_url: str) -> str:
    """Extract the canonical file title from a Wikimedia Commons page URL."""
    path = unquote(urlparse(source_page_url).path)
    marker = "/wiki/File:"
    if marker not in path:
        raise ValueError(f"Not a Wikimedia file page: {source_page_url}")
    filename = path.split(marker, 1)[1]
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError(f"Unsafe or empty Wikimedia filename: {filename!r}")
    return filename


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a downloaded file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_receipts(path: Path) -> dict[str, dict[str, str]]:
    """Load prior receipts by record ID so reruns preserve audit history."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as stream:
        return {row["record_id"]: row for row in csv.DictReader(stream)}


def write_receipts(path: Path, receipts: dict[str, dict[str, str]]) -> None:
    """Atomically replace the receipt CSV with records sorted by ID."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=RECEIPT_FIELDS)
        writer.writeheader()
        writer.writerows(receipts[key] for key in sorted(receipts))
    os.replace(temporary, path)


def download_record(
    session: requests.Session,
    record: dict[str, str],
    output_dir: Path,
    max_bytes: int,
    authorization_reference: str,
    retry_attempts: int,
    retry_base_seconds: float,
) -> dict[str, str]:
    """Stream one bounded video download and return its receipt fields."""
    filename = wikimedia_filename(record["source_page_url"])
    suffix = Path(filename).suffix.lower()
    if suffix not in {".webm", ".ogv", ".ogg", ".mpg", ".mpeg"}:
        raise ValueError(f"Unsupported video suffix for {record['record_id']}: {suffix}")

    direct_url = "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + quote(
        filename, safe=""
    )
    destination = output_dir / f"{record['record_id']}{suffix}"
    partial = destination.with_suffix(destination.suffix + ".part")
    output_dir.mkdir(parents=True, exist_ok=True)

    response: requests.Response | None = None
    for attempt in range(retry_attempts):
        candidate = session.get(direct_url, stream=True, timeout=(20, 180))
        if candidate.status_code != 429:
            response = candidate
            break
        retry_after = candidate.headers.get("retry-after", "")
        candidate.close()
        try:
            wait_seconds = float(retry_after)
        except ValueError:
            wait_seconds = retry_base_seconds * (2**attempt)
        wait_seconds = max(retry_base_seconds, min(wait_seconds, 300.0))
        print(
            f"rate_limited={record['record_id']} attempt={attempt + 1}/"
            f"{retry_attempts} wait_seconds={wait_seconds:.0f}"
        )
        time.sleep(wait_seconds)
    if response is None:
        raise RuntimeError(f"Rate limit persisted after {retry_attempts} attempts")

    with response:
        response.raise_for_status()
        content_length = int(response.headers.get("content-length", "0") or 0)
        if content_length > max_bytes:
            raise ValueError(
                f"Refusing {record['record_id']}: {content_length} exceeds {max_bytes} bytes"
            )
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type and not (
            content_type.startswith("video/")
            or content_type in {"application/ogg", "application/octet-stream"}
        ):
            raise ValueError(
                f"Unexpected content type for {record['record_id']}: {content_type}"
            )

        total = 0
        try:
            with partial.open("wb") as stream:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if not block:
                        continue
                    total += len(block)
                    if total > max_bytes:
                        raise ValueError(
                            f"Refusing {record['record_id']}: stream exceeds {max_bytes} bytes"
                        )
                    stream.write(block)
            os.replace(partial, destination)
        finally:
            partial.unlink(missing_ok=True)

    return {
        "record_id": record["record_id"],
        "inventory_status": record["status"],
        "source_page_url": record["source_page_url"],
        "direct_url": response.url,
        "local_path": str(destination.relative_to(ROOT)),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "bytes": str(destination.stat().st_size),
        "sha256": sha256_file(destination),
        "content_type": content_type,
        "etag": response.headers.get("etag", ""),
        "last_modified": response.headers.get("last-modified", ""),
        "authorization_reference": authorization_reference,
    }


def main() -> None:
    """Download eligible inventory records while retaining partial successes."""
    args = parse_args()
    allowed_statuses = {value.strip() for value in args.statuses.split(",") if value.strip()}
    receipts = load_receipts(args.receipts)
    session = requests.Session()
    session.headers["User-Agent"] = "RAG3D-VideoResearch/1.0"

    with args.inventory.open("r", encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))

    selected = [record for record in records if record["status"] in allowed_statuses]
    if not selected:
        raise SystemExit("No inventory records matched the allowed statuses")

    failures: list[str] = []
    completed = 0
    for position, record in enumerate(selected):
        try:
            prior = receipts.get(record["record_id"])
            if prior:
                prior_path = ROOT / prior["local_path"]
                if prior_path.exists() and sha256_file(prior_path) == prior["sha256"]:
                    completed += 1
                    print(
                        f"skipped_existing={record['record_id']} bytes={prior['bytes']} "
                        f"sha256={prior['sha256']}"
                    )
                    continue
            receipt = download_record(
                session,
                record,
                args.output_dir,
                args.max_bytes,
                args.authorization_reference,
                args.retry_attempts,
                args.retry_base_seconds,
            )
            receipts[record["record_id"]] = receipt
            write_receipts(args.receipts, receipts)
            completed += 1
            print(
                f"downloaded={record['record_id']} bytes={receipt['bytes']} "
                f"sha256={receipt['sha256']}"
            )
            if position < len(selected) - 1 and args.delay_seconds > 0:
                time.sleep(args.delay_seconds)
        except Exception as exc:  # Continue so one remote failure does not lose prior receipts.
            failures.append(f"{record['record_id']}: {exc}")
            print(f"failed={record['record_id']} error={exc}")

    print(f"selected={len(selected)} completed={completed} failures={len(failures)}")
    if failures:
        raise SystemExit("; ".join(failures))


if __name__ == "__main__":
    main()
