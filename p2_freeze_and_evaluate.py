#!/usr/bin/env python3
"""Freeze qrels v2 and produce reproducible P2 retrieval/temporal experiments.

The script deliberately treats the source-disjoint test split as write-only:
configuration selection uses development queries, and the selected configuration
is evaluated on test exactly once after selection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


SEED = 20260729
THRESHOLDS = (0.3, 0.5, 0.7)
MODES = ("bm25", "dense", "visual", "hybrid", "tri_hybrid")
WEIGHT_GRID = (
    (0.30, 0.35, 0.35),
    (0.40, 0.30, 0.30),
    (0.20, 0.40, 0.40),
    (0.20, 0.50, 0.30),
    (0.20, 0.30, 0.50),
    (0.45, 0.35, 0.20),
    (0.35, 0.45, 0.20),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write an empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_sha(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    overlap = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return overlap / union if union > 0 else 0.0


def dcg(grades: list[int], k: int) -> float:
    return sum(
        ((2**grade) - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(grades[:k], 1)
    )


def retrieval_metrics(
    query_ids: list[str],
    ranked: dict[str, list[str]],
    grades: dict[str, dict[str, int]],
    k: int = 5,
) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for qid in query_ids:
        positives = sum(g >= 2 for g in grades[qid].values())
        if not positives:
            continue
        returned = ranked[qid][:k]
        returned_grades = [grades[qid].get(scene, 0) for scene in returned]
        hits = [g >= 2 for g in returned_grades]
        ideal = sorted(grades[qid].values(), reverse=True)
        values["recall"].append(sum(hits) / positives)
        values["ndcg"].append(dcg(returned_grades, k) / dcg(ideal, k))
        values["mrr"].append(
            next((1 / rank for rank, hit in enumerate(hits, 1) if hit), 0.0)
        )
    return {name: mean(metric_values) for name, metric_values in values.items()}


def freeze_qrels_v2(
    qrels_path: Path, output_dir: Path
) -> tuple[Path, list[dict[str, str]], list[dict[str, str]]]:
    rows = read_csv(qrels_path)
    by_query: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_query[row["query_id"]].append(row)

    decision_rows: list[dict[str, str]] = []
    output_rows: list[dict[str, str]] = []
    for row in rows:
        leakage = row["source_leakage"]
        eligible = leakage == "no"
        if leakage == "yes":
            decision = "exclude_primary_and_sensitivity"
            reason = (
                "Existing independent human review confirmed source leakage; "
                "grade is preserved and the pair is excluded from primary evaluation."
            )
        elif leakage == "uncertain":
            decision = "exclude_primary_include_sensitivity"
            reason = (
                "Existing human adjudication could not rule out leakage; grade is "
                "preserved, excluded from primary results, and retained for sensitivity."
            )
        else:
            decision = "include_primary"
            reason = "Existing adjudication records source_leakage=no."
        enriched = dict(row)
        enriched["primary_eval_eligible"] = "yes" if eligible else "no"
        enriched["sensitivity_eval_eligible"] = (
            "yes" if leakage in {"no", "uncertain"} else "no"
        )
        enriched["v2_policy_decision"] = decision
        output_rows.append(enriched)
        if leakage != "no":
            decision_rows.append(
                {
                    "query_id": row["query_id"],
                    "candidate_scene_id": row["candidate_scene_id"],
                    "relevance_grade_preserved": row["relevance_grade"],
                    "v1_source_leakage": leakage,
                    "v2_policy_decision": decision,
                    "primary_eval_eligible": enriched["primary_eval_eligible"],
                    "sensitivity_eval_eligible": enriched[
                        "sensitivity_eval_eligible"
                    ],
                    "decision_basis": reason,
                    "human_evidence_notes": row["evidence_notes"],
                    "human_correction_reason": row["correction_reason"],
                }
            )

    no_positive: list[dict[str, str]] = []
    for qid, qrows in sorted(by_query.items()):
        if max(int(row["relevance_grade"]) for row in qrows) >= 2:
            continue
        no_positive.append(
            {
                "query_id": qid,
                "query_text": qrows[0]["query_text"],
                "split": qrows[0]["split"],
                "product_class": qrows[0]["product_class"],
                "query_type": qrows[0]["query_type"],
                "classification": "candidate_pool_no_direct_answer",
                "basis": (
                    "All judged candidates have grade <=1; the question is operational "
                    "and answerable in principle, so this is not an unanswerable query."
                ),
                "evaluation_policy": (
                    "exclude from binary pool-relative macro metrics; count as zero in "
                    "coverage-adjusted metrics and include in no-answer analysis"
                ),
            }
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    v2_path = output_dir / "paper_video_qrels_graded_v2.csv"
    write_csv(v2_path, output_rows)
    write_csv(output_dir / "source_leakage_decisions_v2.csv", decision_rows)
    write_csv(output_dir / "no_positive_query_classification_v2.csv", no_positive)
    manifest = {
        "schema_version": "paper-video-qrels-v2",
        "created_at": utc_now(),
        "v1_input": {"path": str(qrels_path), "sha256": sha256(qrels_path)},
        "v2_output": {"path": str(v2_path), "sha256": sha256(v2_path)},
        "row_count": len(output_rows),
        "query_count": len(by_query),
        "grade_changes": 0,
        "source_leakage_decisions": len(decision_rows),
        "no_positive_queries": len(no_positive),
        "primary_policy": "exclude all source_leakage=yes or uncertain pairs",
        "sensitivity_policy": "include uncertain but exclude yes pairs",
        "limitations": (
            "v2 is a predeclared evaluation-policy view over completed human "
            "adjudications; it does not invent new relevance judgments."
        ),
    }
    (output_dir / "paper_video_qrels_manifest_v2.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return v2_path, output_rows, no_positive


def load_pool(
    pool_path: Path,
) -> tuple[
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, list[str]]],
]:
    candidates: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    native: dict[str, dict[str, list[tuple[int, str]]]] = {
        mode: defaultdict(list) for mode in MODES
    }
    for row in read_csv(pool_path):
        ranks = json.loads(row["method_ranks_json"])
        item = {
            "start": float(row["start_seconds"]),
            "end": float(row["end_seconds"]),
            "ranks": ranks,
        }
        candidates[row["query_id"]][row["candidate_scene_id"]] = item
        for mode, rank in ranks.items():
            native[mode][row["query_id"]].append(
                (int(rank), row["candidate_scene_id"])
            )
    ordered: dict[str, dict[str, list[str]]] = {mode: {} for mode in MODES}
    for mode in MODES:
        for qid, items in native[mode].items():
            ordered[mode][qid] = [scene for _, scene in sorted(items)]
    return candidates, ordered


def temporal_evaluation(
    candidates: dict[str, dict[str, dict[str, Any]]],
    native: dict[str, dict[str, list[str]]],
    qrel_rows: list[dict[str, str]],
    output_dir: Path,
) -> None:
    truth: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    meta: dict[str, dict[str, str]] = {}
    for row in qrel_rows:
        if row["primary_eval_eligible"] != "yes" or int(row["relevance_grade"]) < 2:
            continue
        truth[row["query_id"]][row["candidate_scene_id"]].append(
            (float(row["relevant_start_time"]), float(row["relevant_end_time"]))
        )
        meta[row["query_id"]] = {
            "product_class": row["product_class"],
            "query_type": row["query_type"],
            "split": row["split"],
        }

    per_query: list[dict[str, Any]] = []
    for mode in MODES:
        for qid in sorted(truth):
            ranking = native[mode][qid]
            scored: list[float] = []
            for scene in ranking:
                pred = (
                    candidates[qid][scene]["start"],
                    candidates[qid][scene]["end"],
                )
                scored.append(
                    max(
                        (
                            iou(pred, interval)
                            for interval in truth[qid].get(scene, [])
                        ),
                        default=0.0,
                    )
                )
            row: dict[str, Any] = {
                "query_id": qid,
                **meta[qid],
                "mode": mode,
                "top1_iou": f"{(scored[0] if scored else 0.0):.6f}",
            }
            for threshold in THRESHOLDS:
                row[f"r1_iou_{threshold}"] = int(bool(scored) and scored[0] >= threshold)
                hits = [value >= threshold for value in scored]
                relevant_total = sum(
                    max(
                        (
                            iou(
                                (
                                    candidates[qid][scene]["start"],
                                    candidates[qid][scene]["end"],
                                ),
                                interval,
                            )
                            for interval in intervals
                        ),
                        default=0.0,
                    )
                    >= threshold
                    for scene, intervals in truth[qid].items()
                )
                precision_sum = sum(
                    sum(hits[:rank]) / rank
                    for rank, hit in enumerate(hits, 1)
                    if hit
                )
                row[f"temporal_ap_{threshold}"] = (
                    f"{precision_sum / relevant_total:.6f}"
                    if relevant_total
                    else ""
                )
            per_query.append(row)

    summary: list[dict[str, Any]] = []
    for dimension in ("overall", "product_class", "query_type", "split"):
        groups = ["all"] if dimension == "overall" else sorted(
            {row[dimension] for row in per_query}
        )
        for group in groups:
            subset = [
                row
                for row in per_query
                if dimension == "overall" or row[dimension] == group
            ]
            for mode in MODES:
                selected = [row for row in subset if row["mode"] == mode]
                out: dict[str, Any] = {
                    "dimension": dimension,
                    "group": group,
                    "mode": mode,
                    "queries": len(selected),
                    "mean_iou": f"{mean(float(r['top1_iou']) for r in selected):.6f}",
                }
                for threshold in THRESHOLDS:
                    out[f"r1_iou_{threshold}"] = (
                        f"{mean(float(r[f'r1_iou_{threshold}']) for r in selected):.6f}"
                    )
                    aps = [
                        float(r[f"temporal_ap_{threshold}"])
                        for r in selected
                        if r[f"temporal_ap_{threshold}"] != ""
                    ]
                    out[f"temporal_map_{threshold}"] = (
                        f"{mean(aps):.6f}" if aps else ""
                    )
                summary.append(out)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "temporal_metrics_per_query.csv", per_query)
    write_csv(output_dir / "temporal_metrics_summary.csv", summary)
    overall = [
        row for row in summary if row["dimension"] == "overall"
    ]
    lines = [
        "# P2 temporal localization",
        "",
        "Prediction is the native retrieved scene interval. Ground truth is the "
        "human relevant sub-interval. Metrics use only primary-eligible grade>=2 "
        "judgments and are therefore pool-relative.",
        "",
        "| Mode | N | mean IoU | R@1 IoU=.3 | R@1 IoU=.5 | R@1 IoU=.7 | t-mAP .3 | t-mAP .5 | t-mAP .7 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in overall:
        lines.append(
            f"| {row['mode']} | {row['queries']} | {row['mean_iou']} | "
            f"{row['r1_iou_0.3']} | {row['r1_iou_0.5']} | {row['r1_iou_0.7']} | "
            f"{row['temporal_map_0.3']} | {row['temporal_map_0.5']} | "
            f"{row['temporal_map_0.7']} |"
        )
    (output_dir / "temporal_table.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def fused_ranking(
    query_candidates: dict[str, dict[str, Any]],
    weights: tuple[float, float, float],
) -> list[str]:
    mode_names = ("bm25", "dense", "visual")
    scored: list[tuple[float, str]] = []
    for scene, item in query_candidates.items():
        # Censored ranks are assigned 21 because each native run is frozen at Top-20.
        score = sum(
            weight / (60 + int(item["ranks"].get(mode, 21)))
            for mode, weight in zip(mode_names, weights)
        )
        scored.append((score, scene))
    return [scene for _, scene in sorted(scored, key=lambda value: (-value[0], value[1]))]


def optimize_and_generalize(
    candidates: dict[str, dict[str, dict[str, Any]]],
    qrel_rows: list[dict[str, str]],
    output_dir: Path,
    commit: str,
) -> None:
    grades: dict[str, dict[str, int]] = defaultdict(dict)
    meta: dict[str, dict[str, str]] = {}
    for row in qrel_rows:
        if row["primary_eval_eligible"] != "yes":
            continue
        grades[row["query_id"]][row["candidate_scene_id"]] = int(
            row["relevance_grade"]
        )
        meta[row["query_id"]] = {
            "split": row["split"],
            "product_class": row["product_class"],
        }
    dev = sorted(qid for qid in grades if meta[qid]["split"] == "development")
    test = sorted(
        qid for qid in grades if meta[qid]["split"] == "source_disjoint_test"
    )
    experiments: list[dict[str, Any]] = []
    ranked_by_weight: dict[tuple[float, float, float], dict[str, list[str]]] = {}
    for index, weights in enumerate(WEIGHT_GRID, 1):
        rankings = {
            qid: fused_ranking(candidates[qid], weights) for qid in grades
        }
        ranked_by_weight[weights] = rankings
        metrics = retrieval_metrics(dev, rankings, grades, 5)
        experiments.append(
            {
                "experiment_id": f"RET-20260729-{index:03d}",
                "git_commit": commit,
                "dataset": "paper_video_qrels_v2",
                "selection_split": "development",
                "seed": SEED,
                "bm25_weight": weights[0],
                "dense_weight": weights[1],
                "visual_weight": weights[2],
                "recall_at_5": f"{metrics['recall']:.6f}",
                "ndcg_at_5": f"{metrics['ndcg']:.6f}",
                "mrr_at_5": f"{metrics['mrr']:.6f}",
                "test_results_viewed_during_selection": "no",
                "rank_censoring": "missing native Top-20 rank assigned 21",
            }
        )
    best_row = max(
        experiments,
        key=lambda row: (float(row["recall_at_5"]), float(row["ndcg_at_5"])),
    )
    best = (
        float(best_row["bm25_weight"]),
        float(best_row["dense_weight"]),
        float(best_row["visual_weight"]),
    )
    test_metrics = retrieval_metrics(test, ranked_by_weight[best], grades, 5)
    best_config = {
        "experiment_id": best_row["experiment_id"],
        "selected_on": "development",
        "objective": "maximize Recall@5, break ties by nDCG@5",
        "weights": {"bm25": best[0], "dense": best[1], "visual": best[2]},
        "development_metrics": {
            key: float(best_row[f"{key}_at_5"])
            for key in ("recall", "ndcg", "mrr")
        },
        "heldout_test_evaluations": 1,
        "heldout_source_disjoint_test_metrics": test_metrics,
        "limitations": (
            "Post-hoc pooled RRF uses frozen native Top-20 ranks; ranks outside "
            "Top-20 are right-censored at 21. It is an ablation, not a new full-corpus run."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "retrieval_experiments.csv", experiments)
    (output_dir / "best_config_and_heldout.json").write_text(
        json.dumps(best_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Leave-one-product-out: select a configuration without the held-out product,
    # then evaluate the untouched product queries exactly once.
    loo_rows: list[dict[str, Any]] = []
    for product in sorted({value["product_class"] for value in meta.values()}):
        train = [
            qid
            for qid in dev
            if meta[qid]["product_class"] != product
        ]
        heldout = [
            qid for qid in grades if meta[qid]["product_class"] == product
        ]
        selected = max(
            WEIGHT_GRID,
            key=lambda weights: (
                retrieval_metrics(train, ranked_by_weight[weights], grades, 5)[
                    "recall"
                ],
                retrieval_metrics(train, ranked_by_weight[weights], grades, 5)[
                    "ndcg"
                ],
            ),
        )
        metrics = retrieval_metrics(
            heldout, ranked_by_weight[selected], grades, 5
        )
        loo_rows.append(
            {
                "heldout_product": product,
                "train_development_queries": len(train),
                "heldout_queries": len(heldout),
                "bm25_weight": selected[0],
                "dense_weight": selected[1],
                "visual_weight": selected[2],
                "recall_at_5": f"{metrics['recall']:.6f}",
                "ndcg_at_5": f"{metrics['ndcg']:.6f}",
                "mrr_at_5": f"{metrics['mrr']:.6f}",
                "external_dataset": "no",
                "protocol": "leave-one-product-class-out",
            }
        )
    write_csv(output_dir / "leave_one_product_out.csv", loo_rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve()
    release = root / "data_video" / "releases" / "paper_video_retrieval_v1"
    qrels_v1 = (
        release
        / "manifests"
        / "paper_qrels_v1"
        / "paper_video_qrels_graded_v1.csv"
    )
    pool = release / "manifests" / "paper_relevance_pool_audit_v1.csv"
    output = root / "reports" / "p2"
    qrels_dir = root / "data_video" / "manifests" / "paper_qrels_v2"
    v2_path, qrel_rows, no_positive = freeze_qrels_v2(qrels_v1, qrels_dir)
    candidates, native = load_pool(pool)
    temporal_evaluation(
        candidates, native, qrel_rows, output / "temporal_localization"
    )
    optimize_and_generalize(
        candidates,
        qrel_rows,
        output / "retrieval_optimization",
        git_sha(root),
    )
    run = {
        "schema_version": "p2-offline-protocol-v1",
        "experiment_id": "P2-OFFLINE-20260729-001",
        "created_at": utc_now(),
        "git_commit_before_run": git_sha(root),
        "seed": SEED,
        "inputs": {
            "qrels_v1_sha256": sha256(qrels_v1),
            "pool_sha256": sha256(pool),
        },
        "outputs": {
            "qrels_v2": str(v2_path.relative_to(root)),
            "qrels_v2_sha256": sha256(v2_path),
            "no_positive_queries": len(no_positive),
            "temporal": "reports/p2/temporal_localization",
            "retrieval_optimization": "reports/p2/retrieval_optimization",
        },
        "test_selection_policy": (
            "development-only configuration selection; held-out test evaluated once"
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "offline_run_manifest.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(run, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
