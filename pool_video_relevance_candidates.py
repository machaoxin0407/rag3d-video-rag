#!/usr/bin/env python3
"""Pool and blind scene candidates for the formal 100-query relevance study."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from video_rag.dense import DEFAULT_DENSE_INDEX, DEFAULT_VISUAL_DENSE_INDEX, sha256_file
from video_rag.manifest_io import ROOT
from video_rag.retrieval import DEFAULT_EVIDENCE, DEFAULT_INVENTORY, VideoEvidenceRetriever


MODES = ("bm25", "dense", "visual", "hybrid", "tri_hybrid")
AUDIT_FIELDS = [
    "query_id", "query_text", "language", "product_class", "query_type", "split",
    "candidate_scene_id", "record_id", "scene_product_class", "start_seconds",
    "end_seconds", "clip_path", "thumbnail_path", "scene_text", "source_methods",
    "method_ranks_json", "method_scores_json", "blind_order",
]
BLIND_FIELDS = [
    "query_id", "query_text", "language", "product_class", "query_type", "split",
    "candidate_scene_id", "record_id", "start_seconds", "end_seconds", "clip_path",
    "thumbnail_path", "scene_text", "blind_order", "ai_relevance_grade",
    "ai_start_time", "ai_end_time", "ai_evidence", "ai_uncertainty",
    "r1_relevance_grade", "r1_start_time", "r1_end_time", "r1_source_leakage",
    "correction_reason", "review_status", "reviewed_at",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queries",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "paper_video_queries_v1.csv",
    )
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--dense-index", type=Path, default=DEFAULT_DENSE_INDEX)
    parser.add_argument("--visual-index", type=Path, default=DEFAULT_VISUAL_DENSE_INDEX)
    parser.add_argument("--dense-endpoint", default=os.getenv("VIDEO_DENSE_ENDPOINT", ""))
    parser.add_argument("--visual-endpoint", default=os.getenv("VIDEO_VISUAL_DENSE_ENDPOINT", ""))
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--top-k-per-mode", type=int, default=20)
    parser.add_argument("--blind-seed", default="paper-relevance-pool-v1")
    parser.add_argument(
        "--audit-output",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "paper_relevance_pool_audit_v1.csv",
    )
    parser.add_argument(
        "--blind-output",
        type=Path,
        default=ROOT / "data_video" / "review" / "paper_relevance_pool_blind_v1.csv",
    )
    parser.add_argument(
        "--run-manifest",
        type=Path,
        default=ROOT / "data_video" / "manifests" / "paper_relevance_pool_run_v1.json",
    )
    parser.add_argument("--require-all-modes", action="store_true")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def blind_key(seed: str, query_id: str, scene_id: str) -> str:
    return hashlib.sha256(f"{seed}\0{query_id}\0{scene_id}".encode()).hexdigest()


def maybe_sha256(path: Path) -> str:
    return sha256_file(path) if path.is_file() else ""


def manifest_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def main() -> None:
    args = parse_args()
    queries = read_csv(args.queries)
    if len(queries) != 100 or len({row["query_id"] for row in queries}) != 100:
        raise ValueError("Formal query input must contain 100 unique query IDs")
    retriever = VideoEvidenceRetriever(
        evidence_path=args.evidence,
        inventory_path=args.inventory,
        dense_index_path=args.dense_index,
        visual_index_path=args.visual_index,
        mode="bm25",
        dense_endpoint=args.dense_endpoint,
        visual_endpoint=args.visual_endpoint,
    )
    if args.require_all_modes:
        if any(mode in {"dense", "hybrid", "tri_hybrid"} for mode in args.modes):
            if retriever.dense_index is None or not args.dense_endpoint:
                raise ValueError("Dense index and endpoint are required")
        if any(mode in {"visual", "tri_hybrid"} for mode in args.modes):
            if retriever.visual_index is None or not args.visual_endpoint:
                raise ValueError("Visual index and endpoint are required")

    audit_rows: list[dict[str, object]] = []
    mode_effective_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    per_query_counts: dict[str, int] = {}
    for query in queries:
        detected = retriever.detect_product_classes(query["query_text"])
        if detected != {query["product_class"]}:
            raise ValueError(
                f"Query routing mismatch for {query['query_id']}: "
                f"expected {query['product_class']}, detected {sorted(detected)}"
            )
        pooled: dict[str, dict[str, object]] = {}
        for mode in args.modes:
            results = retriever.search(query["query_text"], top_k=args.top_k_per_mode, mode=mode)
            for rank, result in enumerate(results, start=1):
                mode_effective_counts[mode][result.retrieval_mode] += 1
                if result.product_class != query["product_class"]:
                    raise ValueError(
                        f"Cross-product result for {query['query_id']}: "
                        f"{result.scene_id} is {result.product_class}"
                    )
                row = pooled.setdefault(
                    result.scene_id,
                    {
                        "result": result,
                        "ranks": {},
                        "scores": {},
                    },
                )
                row["ranks"][mode] = rank
                row["scores"][mode] = {
                    "score": result.score,
                    "bm25_score": result.bm25_score,
                    "dense_score": result.dense_score,
                    "visual_score": result.visual_score,
                    "effective_mode": result.retrieval_mode,
                }
        ordered = sorted(
            pooled.items(),
            key=lambda item: blind_key(args.blind_seed, query["query_id"], item[0]),
        )
        per_query_counts[query["query_id"]] = len(ordered)
        for blind_order, (scene_id, payload) in enumerate(ordered, start=1):
            result = payload["result"]
            ranks = payload["ranks"]
            audit_rows.append(
                {
                    "query_id": query["query_id"],
                    "query_text": query["query_text"],
                    "language": query["language"],
                    "product_class": query["product_class"],
                    "query_type": query["query_type"],
                    "split": query["split"],
                    "candidate_scene_id": scene_id,
                    "record_id": result.record_id,
                    "scene_product_class": result.product_class,
                    "start_seconds": result.start_seconds,
                    "end_seconds": result.end_seconds,
                    "clip_path": result.clip_path,
                    "thumbnail_path": result.thumbnail_path,
                    "scene_text": result.text,
                    "source_methods": "|".join(sorted(ranks)),
                    "method_ranks_json": json.dumps(ranks, sort_keys=True),
                    "method_scores_json": json.dumps(payload["scores"], sort_keys=True),
                    "blind_order": blind_order,
                }
            )

    audit_rows.sort(key=lambda row: (row["query_id"], int(row["blind_order"])))
    blind_rows: list[dict[str, object]] = []
    for row in audit_rows:
        blind = {field: row.get(field, "") for field in BLIND_FIELDS}
        blind["review_status"] = "pending"
        blind_rows.append(blind)
    write_csv(args.audit_output, AUDIT_FIELDS, audit_rows)
    write_csv(args.blind_output, BLIND_FIELDS, blind_rows)

    manifest = {
        "schema_version": "paper-relevance-pool-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "query_count": len(queries),
        "pooled_pair_count": len(audit_rows),
        "per_query_min": min(per_query_counts.values()),
        "per_query_max": max(per_query_counts.values()),
        "per_query_mean": sum(per_query_counts.values()) / len(per_query_counts),
        "modes": args.modes,
        "top_k_per_mode": args.top_k_per_mode,
        "blind_seed": args.blind_seed,
        "effective_mode_counts": {key: dict(value) for key, value in mode_effective_counts.items()},
        "inputs": {
            "queries": manifest_path(args.queries),
            "queries_sha256": sha256_file(args.queries),
            "evidence": manifest_path(args.evidence),
            "evidence_sha256": sha256_file(args.evidence),
            "inventory": manifest_path(args.inventory),
            "inventory_sha256": sha256_file(args.inventory),
            "dense_index_sha256": maybe_sha256(args.dense_index),
            "visual_index_sha256": maybe_sha256(args.visual_index),
        },
        "outputs": {
            "audit": manifest_path(args.audit_output),
            "blind": manifest_path(args.blind_output),
        },
    }
    args.run_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.run_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
