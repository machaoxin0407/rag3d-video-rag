#!/usr/bin/env python3
"""Evaluate five frozen retrieval runs against adjudicated graded qrels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


MODES = ("bm25", "dense", "visual", "hybrid", "tri_hybrid")
CUTOFFS = (1, 5, 10, 20)
BINARY_THRESHOLD = 2
BOOTSTRAP_SAMPLES = 10000
BOOTSTRAP_SEED = 20260729


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--qrels-manifest", type=Path, required=True)
    parser.add_argument("--pool-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def gain(grade: int) -> int:
    return (2**grade) - 1


def dcg(grades: list[int], cutoff: int) -> float:
    return sum(
        gain(grade) / math.log2(rank + 1)
        for rank, grade in enumerate(grades[:cutoff], start=1)
    )


def query_metrics(
    ranked_scene_ids: list[str],
    qrels: dict[str, int],
    cutoff: int,
) -> dict[str, float | None]:
    grades = [qrels.get(scene_id, 0) for scene_id in ranked_scene_ids[:cutoff]]
    ideal = sorted(qrels.values(), reverse=True)
    ideal_dcg = dcg(ideal, cutoff)
    relevant_total = sum(grade >= BINARY_THRESHOLD for grade in qrels.values())
    binary = [grade >= BINARY_THRESHOLD for grade in grades]
    hits = sum(binary)
    precision = hits / cutoff if relevant_total else None
    recall = hits / relevant_total if relevant_total else None
    reciprocal_rank = next(
        (1.0 / rank for rank, relevant in enumerate(binary, start=1) if relevant),
        0.0,
    )
    precision_sum = sum(
        sum(binary[:rank]) / rank
        for rank, relevant in enumerate(binary, start=1)
        if relevant
    )
    average_precision = (
        precision_sum / relevant_total if relevant_total else None
    )
    return {
        "ndcg": dcg(grades, cutoff) / ideal_dcg if ideal_dcg else None,
        "map": average_precision,
        "mrr": reciprocal_rank if relevant_total else None,
        "recall": recall,
        "precision": precision,
        "hit": float(hits > 0) if relevant_total else None,
    }


def macro(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return mean(valid) if valid else None


def format_metric(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def bootstrap_difference(
    reference: list[float],
    comparison: list[float],
) -> dict[str, float]:
    if len(reference) != len(comparison) or not reference:
        raise ValueError("Paired bootstrap inputs must be non-empty and aligned")
    rng = random.Random(BOOTSTRAP_SEED)
    differences: list[float] = []
    count = len(reference)
    for _ in range(BOOTSTRAP_SAMPLES):
        indices = [rng.randrange(count) for _ in range(count)]
        differences.append(
            mean(reference[index] - comparison[index] for index in indices)
        )
    differences.sort()
    observed = mean(reference) - mean(comparison)
    lower = differences[int(0.025 * BOOTSTRAP_SAMPLES)]
    upper = differences[int(0.975 * BOOTSTRAP_SAMPLES)]
    nonpositive = (
        sum(value <= 0 for value in differences) + 1
    ) / (BOOTSTRAP_SAMPLES + 1)
    nonnegative = (
        sum(value >= 0 for value in differences) + 1
    ) / (BOOTSTRAP_SAMPLES + 1)
    return {
        "observed_difference": observed,
        "ci95_low": lower,
        "ci95_high": upper,
        "two_sided_p": min(1.0, 2 * min(nonpositive, nonnegative)),
    }


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    for path in (args.pool, args.qrels, args.qrels_manifest, args.pool_manifest):
        if not path.is_file():
            raise FileNotFoundError(path)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    qrel_rows = read_csv(args.qrels)
    pool_rows = read_csv(args.pool)
    qrels_by_query: dict[str, dict[str, int]] = defaultdict(dict)
    metadata: dict[str, dict[str, str]] = {}
    for row in qrel_rows:
        query_id = row["query_id"]
        scene_id = row["candidate_scene_id"]
        if scene_id in qrels_by_query[query_id]:
            raise ValueError(f"Duplicate qrel: {query_id} {scene_id}")
        qrels_by_query[query_id][scene_id] = int(row["relevance_grade"])
        current = {
            "language": row["language"],
            "product_class": row["product_class"],
            "query_type": row["query_type"],
            "split": row["split"],
        }
        if query_id in metadata and metadata[query_id] != current:
            raise ValueError(f"Inconsistent query metadata: {query_id}")
        metadata[query_id] = current
    if len(qrel_rows) != 3775 or len(qrels_by_query) != 100:
        raise ValueError("Formal qrels coverage is not 3775 pairs / 100 queries")

    runs: dict[str, dict[str, list[tuple[int, str, str]]]] = {
        mode: defaultdict(list) for mode in MODES
    }
    pool_pairs: set[tuple[str, str]] = set()
    for row in pool_rows:
        pair = (row["query_id"], row["candidate_scene_id"])
        pool_pairs.add(pair)
        ranks = json.loads(row["method_ranks_json"])
        scores = json.loads(row["method_scores_json"])
        for mode, rank in ranks.items():
            if mode not in MODES:
                raise ValueError(f"Unknown retrieval mode: {mode}")
            effective = scores[mode]["effective_mode"]
            if effective != mode:
                raise ValueError(f"{mode} fell back to {effective} for {pair}")
            runs[mode][row["query_id"]].append(
                (int(rank), row["candidate_scene_id"], effective)
            )
    qrel_pairs = {
        (query_id, scene_id)
        for query_id, judgments in qrels_by_query.items()
        for scene_id in judgments
    }
    if qrel_pairs != pool_pairs:
        raise ValueError(
            f"Pool/qrels pair mismatch: qrels_only={len(qrel_pairs-pool_pairs)} "
            f"pool_only={len(pool_pairs-qrel_pairs)}"
        )

    ranked: dict[str, dict[str, list[str]]] = {mode: {} for mode in MODES}
    for mode in MODES:
        if set(runs[mode]) != set(qrels_by_query):
            raise ValueError(f"{mode} does not cover all queries")
        for query_id, items in runs[mode].items():
            items.sort()
            ranks = [item[0] for item in items]
            if ranks != list(range(1, len(items) + 1)):
                raise ValueError(f"{mode}/{query_id} ranks are not contiguous")
            if len(items) > 20:
                raise ValueError(f"{mode}/{query_id} exceeds frozen Top-20")
            scene_ids = [item[1] for item in items]
            if len(scene_ids) != len(set(scene_ids)):
                raise ValueError(f"{mode}/{query_id} contains duplicate scenes")
            ranked[mode][query_id] = scene_ids

    per_query_rows: list[dict[str, Any]] = []
    metric_store: dict[str, dict[int, dict[str, list[float | None]]]] = {
        mode: {
            cutoff: {
                metric: []
                for metric in ("ndcg", "map", "mrr", "recall", "precision", "hit")
            }
            for cutoff in CUTOFFS
        }
        for mode in MODES
    }
    query_ids = sorted(qrels_by_query)
    for query_id in query_ids:
        relevant_count = sum(
            grade >= BINARY_THRESHOLD
            for grade in qrels_by_query[query_id].values()
        )
        for mode in MODES:
            for cutoff in CUTOFFS:
                values = query_metrics(
                    ranked[mode][query_id],
                    qrels_by_query[query_id],
                    cutoff,
                )
                for metric, value in values.items():
                    metric_store[mode][cutoff][metric].append(value)
                per_query_rows.append({
                    "query_id": query_id,
                    **metadata[query_id],
                    "relevant_ge2_in_pool": relevant_count,
                    "mode": mode,
                    "cutoff": cutoff,
                    **{
                        metric: format_metric(value)
                        for metric, value in values.items()
                    },
                })

    summary_rows: list[dict[str, Any]] = []
    for mode in MODES:
        for cutoff in CUTOFFS:
            row: dict[str, Any] = {
                "mode": mode,
                "cutoff": cutoff,
                "total_queries": len(query_ids),
                "graded_evaluable_queries": sum(
                    value is not None
                    for value in metric_store[mode][cutoff]["ndcg"]
                ),
                "binary_evaluable_queries": sum(
                    value is not None
                    for value in metric_store[mode][cutoff]["recall"]
                ),
            }
            for metric, values in metric_store[mode][cutoff].items():
                row[metric] = format_metric(macro(values))
                if metric != "ndcg":
                    row[f"{metric}_all_queries"] = format_metric(
                        mean(0.0 if value is None else value for value in values)
                    )
            summary_rows.append(row)

    breakdown_rows: list[dict[str, Any]] = []
    for dimension in ("product_class", "query_type", "language", "split"):
        values = sorted({metadata[query_id][dimension] for query_id in query_ids})
        for group in values:
            selected = [
                index
                for index, query_id in enumerate(query_ids)
                if metadata[query_id][dimension] == group
            ]
            for mode in MODES:
                cutoff = 10
                row = {
                    "dimension": dimension,
                    "group": group,
                    "mode": mode,
                    "cutoff": cutoff,
                    "queries": len(selected),
                }
                for metric in ("ndcg", "map", "mrr", "recall", "precision", "hit"):
                    row[metric] = format_metric(
                        macro([
                            metric_store[mode][cutoff][metric][index]
                            for index in selected
                        ])
                    )
                breakdown_rows.append(row)

    significance = {}
    reference = [
        float(value)
        for value in metric_store["tri_hybrid"][10]["ndcg"]
        if value is not None
    ]
    for mode in MODES:
        if mode == "tri_hybrid":
            continue
        comparison = [
            float(value)
            for value in metric_store[mode][10]["ndcg"]
            if value is not None
        ]
        significance[f"tri_hybrid_vs_{mode}_ndcg_at_10"] = (
            bootstrap_difference(reference, comparison)
        )
    run_depth = {
        mode: {
            "total_results": sum(len(items) for items in ranked[mode].values()),
            "minimum_per_query": min(len(items) for items in ranked[mode].values()),
            "maximum_per_query": max(len(items) for items in ranked[mode].values()),
            "mean_per_query": mean(len(items) for items in ranked[mode].values()),
        }
        for mode in MODES
    }

    write_csv(
        output_dir / "paper_retrieval_metrics_summary_v1.csv",
        list(summary_rows[0]),
        summary_rows,
    )
    write_csv(
        output_dir / "paper_retrieval_metrics_per_query_v1.csv",
        list(per_query_rows[0]),
        per_query_rows,
    )
    write_csv(
        output_dir / "paper_retrieval_metrics_breakdown_v1.csv",
        list(breakdown_rows[0]),
        breakdown_rows,
    )

    primary_rows = [
        row for row in summary_rows if row["cutoff"] in {10, 20}
    ]
    table_rows = [
        [
            row["mode"],
            str(row["cutoff"]),
            str(row["binary_evaluable_queries"]),
            f"{float(row['ndcg']):.3f}",
            f"{float(row['map']):.3f}",
            f"{float(row['mrr']):.3f}",
            f"{float(row['recall']):.3f}",
            f"{float(row['precision']):.3f}",
        ]
        for row in primary_rows
    ]
    significance_rows = []
    for key, values in significance.items():
        comparison = key.removeprefix("tri_hybrid_vs_").removesuffix(
            "_ndcg_at_10"
        )
        significance_rows.append([
            comparison,
            f"{values['observed_difference']:.3f}",
            f"[{values['ci95_low']:.3f}, {values['ci95_high']:.3f}]",
            f"{values['two_sided_p']:.4f}",
        ])
    product_groups = sorted({
        row["group"]
        for row in breakdown_rows
        if row["dimension"] == "product_class"
    })
    product_rows = []
    for group in product_groups:
        by_mode = {
            row["mode"]: row
            for row in breakdown_rows
            if row["dimension"] == "product_class" and row["group"] == group
        }
        product_rows.append([
            group,
            str(next(iter(by_mode.values()))["queries"]),
            *[f"{float(by_mode[mode]['ndcg']):.3f}" for mode in MODES],
        ])
    paper_markdown = f"""# Formal video retrieval evaluation

Generated: {datetime.now(timezone.utc).isoformat()}

Primary binary relevance is grade >= {BINARY_THRESHOLD}. Graded nDCG uses
gain $2^{{grade}}-1$. All rankings are the frozen native Top-20 outputs pooled
across BM25, dense, visual, hybrid, and tri-hybrid. Unjudged scenes outside the
pool are not known relevant; recall and MAP are therefore pool-relative.
Queries without any grade >= 2 judgment are excluded from binary macro metrics.
The summary CSV/JSON also contains `_all_queries` variants that score those
no-positive queries as zero, providing a conservative coverage-adjusted view.

## Main table

{markdown_table(
    ["Mode", "K", "N_bin", "nDCG", "MAP", "MRR", "Recall", "Precision"],
    table_rows,
)}

## Paired bootstrap on nDCG@10

10,000 paired query bootstrap samples, seed {BOOTSTRAP_SEED}; reference is
tri-hybrid.

{markdown_table(
    ["Comparison", "Delta", "95% CI", "Two-sided p"],
    significance_rows,
)}

## nDCG@10 by product class

{markdown_table(
    ["Product", "Queries", *MODES],
    product_rows,
)}
"""
    (output_dir / "paper_retrieval_table_v1.md").write_text(
        paper_markdown, encoding="utf-8"
    )
    report = {
        "schema_version": "paper-video-retrieval-evaluation-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "modes": list(MODES),
        "cutoffs": list(CUTOFFS),
        "primary_binary_threshold": BINARY_THRESHOLD,
        "graded_gain": "2^grade - 1",
        "top_k_run_depth": 20,
        "pool_relative_metrics": True,
        "total_queries": len(query_ids),
        "queries_with_grade_ge_2": sum(
            any(grade >= BINARY_THRESHOLD for grade in judgments.values())
            for judgments in qrels_by_query.values()
        ),
        "run_depth": run_depth,
        "summary": summary_rows,
        "paired_bootstrap": significance,
        "inputs": {
            "pool": {"path": str(args.pool), "sha256": sha256_file(args.pool)},
            "qrels": {"path": str(args.qrels), "sha256": sha256_file(args.qrels)},
            "pool_manifest": {
                "path": str(args.pool_manifest),
                "sha256": sha256_file(args.pool_manifest),
            },
            "qrels_manifest": {
                "path": str(args.qrels_manifest),
                "sha256": sha256_file(args.qrels_manifest),
            },
        },
    }
    (output_dir / "paper_retrieval_evaluation_v1.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"paper_video_retrieval_evaluation={output_dir}")


if __name__ == "__main__":
    main()
