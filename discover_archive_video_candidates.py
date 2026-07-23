#!/usr/bin/env python3
"""Discover bounded Internet Archive videos for the six-class paper corpus.

The script records search and file-selection evidence but does not download media.
Its seed output can be passed directly to download_archive_video_candidates.py.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


ROOT = Path(__file__).resolve().parent
SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{}"
USER_AGENT = "RAG3D-DatasetBuilder/0.3 (academic dataset audit)"

CONFIG = {
    "Air Fryer": {
        "prefix": "airfryer",
        "queries": ['title:("air fryer")', 'title:(airfryer)'],
        "positive": ("air fryer", "airfryer"),
        "negative": ("commercial", "infomercial", "snapchat", "podcast"),
        "quota": 12,
        "procedure": "air fryer operation, maintenance, or troubleshooting",
    },
    "Espresso Machine": {
        "prefix": "espresso",
        "queries": [
            'title:("espresso machine")',
            'title:("espresso maker")',
            'title:(portafilter espresso)',
            'title:("espresso machine" repair)',
            'title:("espresso machine" clean)',
            'title:("espresso machine" tutorial)',
        ],
        "positive": ("espresso machine", "espresso maker", "portafilter", "espresso"),
        "negative": ("martini", "song", "music", "coffee shop tour", "caption", "magical espresso"),
        "quota": 14,
        "procedure": "espresso machine operation, maintenance, or troubleshooting",
    },
    "Pressure Cooker": {
        "prefix": "pressure",
        "queries": [
            'title:("pressure cooker")',
            'title:("instant pot")',
            'title:("pressure cooker" recipe)',
            'title:("instant pot" recipe)',
            'title:("instant pot" tutorial)',
        ],
        "positive": ("pressure cooker", "instant pot", "instapot"),
        "negative": ("review only", "unboxing only", "arcade", "atari", "commentary", "prostitute"),
        "quota": 18,
        "procedure": "pressure cooker operation, maintenance, or troubleshooting",
    },
    "Printer": {
        "prefix": "printer",
        "queries": [
            'title:("printer setup")',
            'title:("printer cartridge")',
            'title:("paper jam" printer)',
            'title:("printer maintenance")',
            'title:("how to" printer)',
        ],
        "positive": ("printer", "cartridge", "paper jam", "toner"),
        "negative": ("3d printer", "3-d printer", "printing press", "screen printing"),
        "quota": 24,
        "procedure": "paper printer setup, operation, maintenance, or troubleshooting",
    },
    "Vacuum": {
        "prefix": "vacuum",
        "queries": [
            'title:("vacuum cleaner")',
            'title:(vacuuming)',
            'title:("robot vacuum")',
            'title:("vacuum filter")',
            'title:("vacuum cleaner" repair)',
            'title:("vacuum cleaner" clean)',
            'title:("LG Vacuum cleaner")',
            'title:("Samsung" "vacuum")',
        ],
        "positive": ("vacuum cleaner", "vacuuming", "robot vacuum", "vacuum filter"),
        "negative": ("vacuum sealer", "vacuum chamber", "vacuum pump", "space vacuum", "commercial", "goanimate", "mickey", "unboxing"),
        "quota": 22,
        "procedure": "household vacuum operation, maintenance, or troubleshooting",
    },
    "Washing Machine": {
        "prefix": "washing",
        "queries": [
            'title:("washing machine")',
            'title:("washer repair")',
            'title:("washer maintenance")',
            'title:("laundry washer")',
            'title:("washing machine repair")',
            'title:("LG Washer")',
            'title:("Samsung" "washing machine")',
            'title:("washing machine" "how to")',
        ],
        "positive": ("washing machine", "washer", "laundry"),
        "negative": ("pressure washer", "dishwasher", "car wash", "brainwashing", "commercial", "advert", "mickey", "minnie", "map part", "music video"),
        "quota": 22,
        "procedure": "washing machine operation, maintenance, or troubleshooting",
    },
}

ACTION_TERMS = (
    "how to", "tutorial", "setup", "install", "operate", "operation", "use ",
    "using", "clean", "maintenance", "repair", "fix", "troubleshoot", "replace",
    "cartridge", "filter", "cycle", "recipe", "cook", "brew", "jam", "demo",
)

REPORT_FIELDS = [
    "record_id", "product_class", "archive_identifier", "title", "creator",
    "description_excerpt", "source_page_url", "license_url", "selected_file",
    "selected_format", "bytes", "duration_seconds", "width", "height",
    "matched_queries", "discovery_score", "selection_status", "selection_reason",
]
SEED_FIELDS = [
    "record_id", "product_class", "archive_identifier", "procedure_or_scene",
    "candidate_split",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "archive_discovery_20260723.csv",
    )
    parser.add_argument(
        "--seeds-output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "archive_candidate_seeds_20260723.csv",
    )
    parser.add_argument("--rows-per-query", type=int, default=60)
    parser.add_argument("--max-bytes", type=int, default=350_000_000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--class-name", action="append", choices=tuple(CONFIG))
    return parser.parse_args()


def plain(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def numeric(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def duration_seconds(value: Any) -> float:
    text = plain(value)
    try:
        return float(text)
    except ValueError:
        pass
    parts = text.split(":")
    try:
        total = 0.0
        for part in parts:
            total = total * 60 + float(part)
        return total
    except ValueError:
        return 0.0


def choose_video_file(files: list[dict[str, Any]], max_bytes: int) -> dict[str, Any] | None:
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for item in files:
        name = plain(item.get("name"))
        lower = name.lower()
        size = numeric(item.get("size"))
        if not lower.endswith((".mp4", ".webm", ".ogv")):
            continue
        if not 500_000 <= size <= max_bytes:
            continue
        if any(token in lower for token in ("sample", "trailer", "thumb", "spectrogram")):
            continue
        duration = duration_seconds(item.get("length"))
        if duration > 1800:
            continue
        height = numeric(item.get("height"))
        width = numeric(item.get("width"))
        fmt = plain(item.get("format")).lower()
        score = 50 if "512kb" in lower else 0
        score += 40 if lower.endswith(".mp4") else 20
        score += 25 if "h.264" in fmt or "mpeg4" in fmt else 0
        score += 20 if 360 <= height <= 720 else 0
        score += min(width // 160, 10)
        ranked.append((score, -size, item))
    return max(ranked, default=(0, 0, None), key=lambda item: (item[0], item[1]))[2]


def request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(4):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=(15, 75))
            if response.status_code in {429, 502, 503, 504}:
                raise requests.HTTPError(f"temporary status {response.status_code}")
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, json.JSONDecodeError):
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def search(query: str, rows: int) -> list[dict[str, Any]]:
    payload = request_json(
        SEARCH_URL,
        {
            "q": f"mediatype:movies AND ({query})",
            "fl[]": ["identifier", "title", "creator", "description", "licenseurl"],
            "rows": rows,
            "page": 1,
            "sort[]": "downloads desc",
            "output": "json",
        },
    )
    return payload.get("response", {}).get("docs", [])


def known_state() -> tuple[set[str], set[str], dict[str, int]]:
    identifiers: set[str] = set()
    record_ids: set[str] = set()
    maximums = defaultdict(int)
    manifests = ROOT / "data_video" / "manifests"
    for path in manifests.glob("*.csv"):
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    record_id = row.get("record_id", "")
                    identifier = row.get("archive_identifier", "")
                    source_url = row.get("source_page_url", "")
                    if record_id:
                        record_ids.add(record_id)
                        match = re.fullmatch(r"([a-z]+)-(\d+)", record_id)
                        if match:
                            maximums[match.group(1)] = max(maximums[match.group(1)], int(match.group(2)))
                    if identifier:
                        identifiers.add(identifier)
                    if "archive.org/details/" in source_url:
                        identifiers.add(source_url.split("archive.org/details/", 1)[1].split("?", 1)[0])
        except (OSError, UnicodeError, csv.Error):
            continue
    return identifiers, record_ids, maximums


def metadata_row(
    product_class: str,
    identifier: str,
    matched_queries: list[str],
    max_bytes: int,
) -> dict[str, Any]:
    config = CONFIG[product_class]
    payload = request_json(METADATA_URL.format(quote(identifier, safe="")))
    metadata = payload.get("metadata", {})
    title = plain(metadata.get("title")) or identifier
    description = plain(metadata.get("description"))
    combined = f"{title} {description}".lower()
    selected = choose_video_file(payload.get("files", []), max_bytes)
    positive = any(term in combined for term in config["positive"])
    negative_hits = [term for term in config["negative"] if term in combined]
    action_hits = sum(term in combined for term in ACTION_TERMS)
    score = 4 * int(positive) + min(action_hits, 5) - 4 * len(negative_hits)
    status = "eligible"
    reasons: list[str] = []
    if not positive:
        status = "reject_metadata"
        reasons.append("no class term in title/description")
    if negative_hits:
        status = "reject_metadata"
        reasons.append("negative terms: " + ", ".join(negative_hits))
    if selected is None:
        status = "reject_file"
        reasons.append("no bounded video file")
    result = {
        "product_class": product_class,
        "archive_identifier": identifier,
        "title": title,
        "creator": plain(metadata.get("creator")) or "Archive contributor",
        "description_excerpt": description[:500],
        "source_page_url": f"https://archive.org/details/{identifier}",
        "license_url": plain(metadata.get("licenseurl")),
        "matched_queries": " | ".join(sorted(matched_queries)),
        "discovery_score": str(score),
        "selection_status": status,
        "selection_reason": "; ".join(reasons),
    }
    if selected:
        result.update(
            {
                "selected_file": plain(selected.get("name")),
                "selected_format": plain(selected.get("format")),
                "bytes": str(numeric(selected.get("size"))),
                "duration_seconds": str(duration_seconds(selected.get("length")) or ""),
                "width": str(numeric(selected.get("width")) or ""),
                "height": str(numeric(selected.get("height")) or ""),
            }
        )
    return result


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    classes = args.class_name or list(CONFIG)
    known_identifiers, record_ids, maximums = known_state()
    matches: dict[tuple[str, str], set[str]] = defaultdict(set)
    for product_class in classes:
        for query in CONFIG[product_class]["queries"]:
            try:
                docs = search(query, args.rows_per_query)
            except Exception as exc:
                print(f"search_failed={product_class!r} query={query!r} error={exc}")
                continue
            for doc in docs:
                identifier = plain(doc.get("identifier"))
                if identifier and identifier not in known_identifiers:
                    matches[(product_class, identifier)].add(query)
            print(f"searched={product_class!r} query={query!r} docs={len(docs)}")

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(metadata_row, cls, identifier, sorted(queries), args.max_bytes): (cls, identifier)
            for (cls, identifier), queries in matches.items()
        }
        for future in as_completed(futures):
            product_class, identifier = futures[future]
            try:
                rows.append(future.result())
            except Exception as exc:
                rows.append(
                    {
                        "product_class": product_class,
                        "archive_identifier": identifier,
                        "source_page_url": f"https://archive.org/details/{identifier}",
                        "selection_status": "metadata_error",
                        "selection_reason": f"{type(exc).__name__}: {exc}",
                    }
                )

    selected: list[dict[str, Any]] = []
    for product_class in classes:
        eligible = [row for row in rows if row["product_class"] == product_class and row["selection_status"] == "eligible"]
        eligible.sort(key=lambda row: (-int(row["discovery_score"]), int(row.get("bytes") or 0), row["archive_identifier"]))
        quota = CONFIG[product_class]["quota"]
        selected.extend(eligible[:quota])
        for row in eligible[:quota]:
            row["selection_status"] = "selected_for_download"
        print(f"eligible={product_class!r} count={len(eligible)} selected={min(len(eligible), quota)} quota={quota}")

    selected_ids = {id(row) for row in selected}
    rows.sort(
        key=lambda row: (
            list(CONFIG).index(row["product_class"]),
            0 if id(row) in selected_ids else 1,
            -int(row.get("discovery_score") or -999),
            row["archive_identifier"],
        )
    )
    seed_rows: list[dict[str, str]] = []
    for row in selected:
        prefix = CONFIG[row["product_class"]]["prefix"]
        while True:
            maximums[prefix] += 1
            record_id = f"{prefix}-{maximums[prefix]:03d}"
            if record_id not in record_ids:
                record_ids.add(record_id)
                break
        row["record_id"] = record_id
        seed_rows.append(
            {
                "record_id": record_id,
                "product_class": row["product_class"],
                "archive_identifier": row["archive_identifier"],
                "procedure_or_scene": CONFIG[row["product_class"]]["procedure"],
                "candidate_split": "development_candidate",
            }
        )

    write_csv(args.report, REPORT_FIELDS, rows)
    write_csv(args.seeds_output, SEED_FIELDS, seed_rows)
    print(f"report={args.report} rows={len(rows)}")
    print(f"seeds={args.seeds_output} rows={len(seed_rows)}")


if __name__ == "__main__":
    main()
