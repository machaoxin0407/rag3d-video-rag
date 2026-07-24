#!/usr/bin/env python3
"""Validate the blinded five-method candidate pool for the 100-query study."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from video_rag.manifest_io import ROOT


MODES = {"bm25", "dense", "visual", "hybrid", "tri_hybrid"}
LABEL_FIELDS = [
    "ai_relevance_grade",
    "ai_start_time",
    "ai_end_time",
    "ai_evidence",
    "ai_uncertainty",
    "r1_relevance_grade",
    "r1_start_time",
    "r1_end_time",
    "r1_source_leakage",
    "correction_reason",
    "reviewed_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queries",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "paper_video_queries_v1.csv",
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "paper_relevance_pool_audit_v1.csv",
    )
    parser.add_argument(
        "--blind",
        type=Path,
        default=ROOT / "data_video" / "review" / "paper_relevance_pool_blind_v1.csv",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "paper_relevance_pool_run_v1.json",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()
    queries = read_csv(args.queries)
    audit = read_csv(args.audit)
    blind = read_csv(args.blind)
    manifest = json.loads(args.run_manifest.read_text(encoding="utf-8"))
    query_by_id = {row["query_id"]: row for row in queries}
    if len(queries) != 100 or len(query_by_id) != 100:
        raise ValueError("Query design must contain 100 unique IDs")
    if len(audit) != len(blind) or not audit:
        raise ValueError("Audit and blind pool counts differ or are empty")

    audit_by_pair: dict[tuple[str, str], dict[str, str]] = {}
    blind_by_pair: dict[tuple[str, str], dict[str, str]] = {}
    orders: dict[str, list[int]] = defaultdict(list)
    method_coverage = Counter()
    for row in audit:
        query = query_by_id.get(row["query_id"])
        if not query:
            raise ValueError(f"Unknown query ID in audit pool: {row['query_id']}")
        if row["product_class"] != query["product_class"]:
            raise ValueError(f"Query class changed for {row['query_id']}")
        if row["scene_product_class"] != query["product_class"]:
            raise ValueError(f"Cross-product candidate: {row['query_id']} {row['candidate_scene_id']}")
        pair = (row["query_id"], row["candidate_scene_id"])
        if pair in audit_by_pair:
            raise ValueError(f"Duplicate audit pair: {pair}")
        audit_by_pair[pair] = row
        orders[row["query_id"]].append(int(row["blind_order"]))
        methods = set(row["source_methods"].split("|"))
        if not methods or not methods <= MODES:
            raise ValueError(f"Invalid source methods for {pair}: {methods}")
        ranks = json.loads(row["method_ranks_json"])
        scores = json.loads(row["method_scores_json"])
        if set(ranks) != methods or set(scores) != methods:
            raise ValueError(f"Rank/score method mismatch for {pair}")
        method_coverage.update(methods)

    for query_id, values in orders.items():
        if sorted(values) != list(range(1, len(values) + 1)):
            raise ValueError(f"Blind order is not contiguous for {query_id}")
    if set(orders) != set(query_by_id):
        raise ValueError("Some formal queries have no pooled candidates")

    for row in blind:
        pair = (row["query_id"], row["candidate_scene_id"])
        if pair in blind_by_pair:
            raise ValueError(f"Duplicate blind pair: {pair}")
        blind_by_pair[pair] = row
        audit_row = audit_by_pair.get(pair)
        if not audit_row:
            raise ValueError(f"Blind pair absent from audit pool: {pair}")
        for field in (
            "query_text",
            "language",
            "product_class",
            "query_type",
            "split",
            "record_id",
            "start_seconds",
            "end_seconds",
            "clip_path",
            "thumbnail_path",
            "scene_text",
            "blind_order",
        ):
            if row[field] != audit_row[field]:
                raise ValueError(f"Blind/audit mismatch for {pair}: {field}")
        if any(row.get(field, "") for field in LABEL_FIELDS):
            raise ValueError(f"Blind row contains premature labels: {pair}")
        if row.get("review_status") != "pending":
            raise ValueError(f"Blind row is not pending: {pair}")
    if set(blind_by_pair) != set(audit_by_pair):
        raise ValueError("Audit and blind pair sets differ")

    requested_modes = manifest.get("modes", [])
    if set(requested_modes) != MODES:
        raise ValueError(f"Run did not request all five modes: {requested_modes}")
    effective = manifest.get("effective_mode_counts", {})
    for mode in requested_modes:
        counts = effective.get(mode, {})
        if set(counts) != {mode} or counts[mode] <= 0:
            raise ValueError(f"Retrieval mode silently fell back: {mode} -> {counts}")
    if manifest.get("query_count") != 100 or manifest.get("pooled_pair_count") != len(audit):
        raise ValueError("Run-manifest counts differ from pool files")
    if manifest["inputs"]["queries_sha256"] != sha256(args.queries):
        raise ValueError("Query hash differs from run manifest")
    print(
        json.dumps(
            {
                "queries": len(queries),
                "pooled_pairs": len(audit),
                "per_query_min": min(len(value) for value in orders.values()),
                "per_query_max": max(len(value) for value in orders.values()),
                "method_coverage": dict(method_coverage),
                "all_modes_native": True,
                "blind_labels_empty": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
