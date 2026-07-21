#!/usr/bin/env python3
"""Collect licensed Wikimedia video candidates for the six-class Video RAG set.

The collector writes a quarantine inventory plus record-specific 480p (or best
available smaller) download URLs.  It does not promote candidates into the
gold inventory; content/quality checks happen after download.
"""

from __future__ import annotations

import argparse
import csv
import html
import re
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent
API_URL = "https://commons.wikimedia.org/w/api.php"
INVENTORY_FIELDS = [
    "record_id", "product_class", "title", "source_platform",
    "source_page_url", "creator", "license_id", "license_url",
    "license_evidence_url", "license_checked_at", "duration_seconds",
    "width", "height", "language", "procedure_or_scene", "relevance",
    "commercial_use", "modification", "redistribution_rule",
    "personality_or_privacy", "status", "status_reason", "reviewer_1",
    "reviewer_2", "local_file_sha256", "notes",
]

PRODUCTS = {
    "espresso": {
        "class": "Espresso Machine",
        "queries": [
            "espresso machine", "espresso preparation", "portafilter tamping",
            "coffee machine cleaning", "coffee machine operation",
        ],
        "exclude": ["coffee plantation", "coffee climate", "coffee ceremony"],
    },
    "pressure": {
        "class": "Pressure Cooker",
        "queries": [
            "pressure cooker", "panela de pressão", "electric pressure cooker",
            "pressure cooking food",
        ],
        "exclude": ["bomb", "alcohol modification", "flying rhino", "venus"],
    },
    "washing": {
        "class": "Washing Machine",
        "queries": [
            "washing machine", "laundry machine", "washer spin cycle",
            "washing machine operation", "washing machine maintenance",
        ],
        "exclude": ["car wash", "washing hands", "dishwasher", "milk pipeline"],
    },
    "vacuum": {
        "class": "Vacuum",
        "queries": [
            "vacuum cleaner", "vacuuming floor", "robot vacuum cleaner",
            "vacuum cleaner operation", "vacuum cleaner maintenance",
        ],
        "exclude": ["vacuum chamber", "vacuum tube", "outer space", "vacuum pump"],
    },
    "printer": {
        "class": "Printer",
        "queries": [
            "inkjet printer", "laser printer", "printer printing page",
            "printer operation", "printer cartridge",
        ],
        "exclude": ["3d printer", "printing press", "newspaper press", "typewriter"],
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--existing-inventory",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "video_source_inventory.csv",
    )
    parser.add_argument(
        "--output-inventory",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "wikimedia_candidates.csv",
    )
    parser.add_argument(
        "--output-overrides",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "wikimedia_candidate_overrides.csv",
    )
    parser.add_argument("--per-class", type=int, default=20)
    parser.add_argument("--search-limit", type=int, default=50)
    parser.add_argument("--request-delay", type=float, default=1.5)
    return parser.parse_args()


def plain(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def metadata_value(metadata: dict[str, Any], key: str) -> str:
    item = metadata.get(key, {})
    return plain(item.get("value", "") if isinstance(item, dict) else str(item))


def allowed_license(short_name: str) -> bool:
    normalized = short_name.lower().replace("-", " ")
    if "noncommercial" in normalized or " no derivatives" in normalized:
        return False
    if re.search(r"\bnc\b|\bnd\b", normalized):
        return False
    return any(value in normalized for value in ("cc0", "cc by", "public domain"))


def license_url(short_name: str) -> str:
    normalized = short_name.lower()
    if "cc0" in normalized:
        return "https://creativecommons.org/publicdomain/zero/1.0/"
    match = re.search(r"cc\s*by(?:-sa)?\s*([234]\.0)", normalized)
    if match:
        family = "by-sa" if "sa" in normalized else "by"
        return f"https://creativecommons.org/licenses/{family}/{match.group(1)}/"
    if "public domain" in normalized:
        return "https://creativecommons.org/publicdomain/mark/1.0/"
    return ""


def api_get(session: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    for attempt in range(6):
        response = session.get(API_URL, params=params, timeout=(20, 90))
        if response.status_code not in {429, 502, 503}:
            response.raise_for_status()
            return response.json()
        retry_after = response.headers.get("retry-after", "")
        try:
            wait = float(retry_after)
        except ValueError:
            wait = 10.0 * (2**attempt)
        time.sleep(min(max(wait, 10.0), 180.0))
    raise RuntimeError("Wikimedia API remained rate limited after retries")


def choose_download(videoinfo: dict[str, Any]) -> tuple[str, str]:
    derivatives = [
        item for item in videoinfo.get("derivatives", [])
        if item.get("src") and "video/webm" in item.get("type", "")
    ]
    bounded = [item for item in derivatives if 240 <= int(item.get("height", 0)) <= 480]
    if bounded:
        chosen = max(bounded, key=lambda item: int(item.get("height", 0)))
        return chosen["src"], chosen.get("transcodekey", "wikimedia_derivative")
    return videoinfo.get("url", ""), "original"


def load_existing(path: Path) -> tuple[set[str], dict[str, int], set[str]]:
    urls: set[str] = set()
    next_ids: dict[str, int] = defaultdict(lambda: 1)
    creators: set[str] = set()
    if not path.exists():
        return urls, next_ids, creators
    with path.open("r", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            urls.add(row.get("source_page_url", ""))
            creators.add(row.get("creator", "").strip().lower())
            match = re.fullmatch(r"([a-z]+)-(\d+)", row.get("record_id", ""))
            if match:
                next_ids[match.group(1)] = max(next_ids[match.group(1)], int(match.group(2)) + 1)
    return urls, next_ids, creators


def search_product(
    session: requests.Session,
    prefix: str,
    config: dict[str, Any],
    search_limit: int,
    request_delay: float,
) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for query_rank, query in enumerate(config["queries"]):
        payload = api_get(session, {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{query} filetype:video",
            "gsrnamespace": 6,
            "gsrlimit": search_limit,
            "prop": "imageinfo|videoinfo",
            "iiprop": "extmetadata",
            "viprop": "url|size|mime|derivatives",
            "format": "json",
            "formatversion": 2,
        })
        for page in payload.get("query", {}).get("pages", []):
            if not page.get("videoinfo") or not page.get("imageinfo"):
                continue
            video = page["videoinfo"][0]
            metadata = page["imageinfo"][0].get("extmetadata", {})
            source_page = video.get("descriptionurl", "")
            title = page.get("title", "").removeprefix("File:")
            description = metadata_value(metadata, "ImageDescription")
            categories = metadata_value(metadata, "Categories")
            haystack = f"{title} {description} {categories}".lower()
            if any(term in haystack for term in config["exclude"]):
                continue
            short_license = metadata_value(metadata, "LicenseShortName")
            if not allowed_license(short_license):
                continue
            duration = float(video.get("duration", 0) or 0)
            if duration < 3 or duration > 1800:
                continue
            direct_url, variant = choose_download(video)
            if not direct_url:
                continue
            score = 100 - 8 * query_rank
            score += 20 if query.lower() in haystack else 0
            score += min(int(video.get("height", 0) or 0) // 120, 10)
            candidate = {
                "prefix": prefix,
                "product_class": config["class"],
                "title": title,
                "source_page_url": source_page,
                "creator": metadata_value(metadata, "Artist") or "Wikimedia contributor",
                "license_id": short_license,
                "license_url": license_url(short_license),
                "duration_seconds": f"{duration:.3f}".rstrip("0").rstrip("."),
                "width": str(video.get("width", "")),
                "height": str(video.get("height", "")),
                "procedure": query,
                "description": description[:500],
                "score": score,
                "direct_url": direct_url,
                "variant": variant,
            }
            previous = by_url.get(source_page)
            if previous is None or candidate["score"] > previous["score"]:
                by_url[source_page] = candidate
        time.sleep(request_delay)
    return sorted(by_url.values(), key=lambda row: (-row["score"], row["title"].lower()))


def diversify(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    creators: set[str] = set()
    for row in candidates:
        creator = row["creator"].strip().lower()
        if creator and creator not in creators:
            selected.append(row)
            creators.add(creator)
        else:
            deferred.append(row)
        if len(selected) == limit:
            return selected
    selected.extend(deferred[: max(0, limit - len(selected))])
    return selected


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> None:
    args = parse_args()
    existing_urls, next_ids, existing_creators = load_existing(args.existing_inventory)
    session = requests.Session()
    session.headers["User-Agent"] = "RAG3D-DatasetBuilder/0.2 (academic dataset audit)"

    inventory_rows: list[dict[str, str]] = []
    override_rows: list[dict[str, str]] = []
    for prefix, config in PRODUCTS.items():
        found = search_product(
            session, prefix, config, args.search_limit, args.request_delay
        )
        found = [row for row in found if row["source_page_url"] not in existing_urls]
        selected = diversify(found, args.per_class)
        test_creators: set[str] = set()
        for row in selected:
            record_id = f"{prefix}-{next_ids[prefix]:03d}"
            next_ids[prefix] += 1
            creator_key = row["creator"].strip().lower()
            split = "development_candidate"
            if (
                len(test_creators) < 3
                and creator_key
                and creator_key not in existing_creators
                and creator_key not in test_creators
            ):
                split = "source_disjoint_test_candidate"
                test_creators.add(creator_key)
            share_alike = "sa" in row["license_id"].lower()
            inventory_rows.append({
                "record_id": record_id,
                "product_class": row["product_class"],
                "title": row["title"],
                "source_platform": "Wikimedia Commons",
                "source_page_url": row["source_page_url"],
                "creator": row["creator"],
                "license_id": row["license_id"],
                "license_url": row["license_url"],
                "license_evidence_url": row["source_page_url"],
                "license_checked_at": date.today().isoformat(),
                "duration_seconds": row["duration_seconds"],
                "width": row["width"],
                "height": row["height"],
                "language": "und",
                "procedure_or_scene": row["procedure"],
                "relevance": "machine_candidate",
                "commercial_use": "allowed",
                "modification": "allowed",
                "redistribution_rule": (
                    "share-alike attribution required" if share_alike else "attribution/license terms apply"
                ),
                "personality_or_privacy": "pending_content_screen",
                "status": "owner_authorized_candidate",
                "status_reason": "Open-license video; pending automated scope and quality screening",
                "reviewer_1": "Codex-machine-prescreen",
                "reviewer_2": "",
                "local_file_sha256": "",
                "notes": f"{split}; variant={row['variant']}; {row['description']}",
            })
            override_rows.append({"record_id": record_id, "download_url": row["direct_url"]})
        print(f"product={config['class']} discovered={len(found)} selected={len(selected)}")

    write_csv(args.output_inventory, INVENTORY_FIELDS, inventory_rows)
    write_csv(args.output_overrides, ["record_id", "download_url"], override_rows)
    print(f"candidate_inventory={args.output_inventory} records={len(inventory_rows)}")


if __name__ == "__main__":
    main()
