#!/usr/bin/env python3
"""Validate and optionally replay the frozen paper video retrieval v1 release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RELEASE_ROOT = (
    PROJECT_ROOT / "data_video" / "releases" / "paper_video_retrieval_v1"
)
MODES = ("bm25", "dense", "visual", "hybrid", "tri_hybrid")
REPLAY_RESULT_FILES = (
    "paper_retrieval_metrics_summary_v1.csv",
    "paper_retrieval_metrics_per_query_v1.csv",
    "paper_retrieval_metrics_breakdown_v1.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--release-root",
        type=Path,
        default=DEFAULT_RELEASE_ROOT,
        help="Frozen release directory.",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Run the formal evaluation and compare it with frozen results.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_trec_qrels(path: Path) -> dict[tuple[str, str], int]:
    rows: dict[tuple[str, str], int] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            parts = line.rstrip("\n").split()
            require(len(parts) == 4, f"Invalid TREC qrels line {line_number}: {path}")
            query_id, iteration, scene_id, grade = parts
            require(iteration == "0", f"Invalid TREC iteration at line {line_number}")
            key = (query_id, scene_id)
            require(key not in rows, f"Duplicate TREC qrels pair: {key}")
            rows[key] = int(grade)
    return rows


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_payloads(release_root: Path, manifest: dict[str, Any]) -> None:
    payloads = manifest.get("payload_files")
    require(isinstance(payloads, dict) and payloads, "payload_files is missing")
    for relative, expected in payloads.items():
        path = release_root / relative
        require(path.is_file(), f"Missing payload: {relative}")
        require(
            path.stat().st_size == int(expected["bytes"]),
            f"Byte count mismatch: {relative}",
        )
        require(
            sha256_file(path) == expected["sha256"],
            f"SHA-256 mismatch: {relative}",
        )

    checksum_path = release_root / "FILE_HASHES.sha256"
    require(checksum_path.is_file(), "FILE_HASHES.sha256 is missing")
    checksum_entries: dict[str, str] = {}
    with checksum_path.open(encoding="ascii") as handle:
        for line in handle:
            digest, relative = line.rstrip("\n").split("  ", 1)
            require(relative not in checksum_entries, f"Duplicate checksum entry: {relative}")
            checksum_entries[relative] = digest
    require(set(checksum_entries) == set(payloads), "Checksum/payload file set mismatch")
    for relative, expected in payloads.items():
        require(
            checksum_entries[relative] == expected["sha256"],
            f"Checksum manifest mismatch: {relative}",
        )


def validate_dataset_manifests(release_root: Path, scope: dict[str, Any]) -> None:
    manifest_root = release_root / "manifests"
    inventory = read_csv(manifest_root / "video_source_inventory.csv")
    scenes = read_csv(manifest_root / "scene_manifest.csv")
    evidence = read_csv(manifest_root / "video_evidence_manifest.csv")
    queries = read_csv(manifest_root / "paper_video_queries_v1.csv")
    freeze = read_json(manifest_root / "video_dataset_v1_freeze_20260724.json")

    require(len(inventory) == scope["inventory_records"], "Inventory row count mismatch")
    require(len(scenes) == scope["scenes"], "Scene row count mismatch")
    require(len(evidence) == scope["evidence_rows"], "Evidence row count mismatch")
    require(len(queries) == scope["queries"], "Query row count mismatch")
    require(len({row["query_id"] for row in queries}) == len(queries), "Duplicate query_id")
    require(len({row["scene_id"] for row in scenes}) == len(scenes), "Duplicate scene_id")
    require(
        freeze["video_count"] == scope["formal_videos"],
        "Frozen formal video count mismatch",
    )
    require(
        len(freeze["target_classes"]) == scope["product_classes"],
        "Frozen product class count mismatch",
    )
    for name, expected_digest in freeze["manifest_sha256"].items():
        frozen_input = manifest_root / name
        require(frozen_input.is_file(), f"Frozen dataset input is missing: {name}")
        require(
            sha256_file(frozen_input) == expected_digest,
            f"{name} does not match the dataset freeze manifest",
        )
    target_classes = set(freeze["target_classes"])
    formal_inventory = [
        row
        for row in inventory
        if row["product_class"] in target_classes and row["status"] == "accepted"
    ]
    require(
        len(formal_inventory) == freeze["video_count"],
        "Accepted formal inventory count mismatch",
    )
    formal_class_counts = Counter(row["product_class"] for row in formal_inventory)
    require(
        dict(sorted(formal_class_counts.items()))
        == dict(sorted(freeze["class_counts"].items())),
        "Accepted formal inventory class distribution mismatch",
    )


def validate_pool_and_qrels(
    release_root: Path, manifest: dict[str, Any]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    manifest_root = release_root / "manifests"
    pool = read_csv(manifest_root / "paper_relevance_pool_audit_v1.csv")
    qrels = read_csv(
        manifest_root / "paper_qrels_v1" / "paper_video_qrels_graded_v1.csv"
    )
    scope = manifest["scope"]
    judgments = manifest["judgments"]

    require(len(pool) == scope["query_scene_pairs"], "Pool row count mismatch")
    require(len(qrels) == scope["query_scene_pairs"], "Qrels row count mismatch")

    pool_pairs = {
        (row["query_id"], row["candidate_scene_id"])
        for row in pool
    }
    qrel_pairs = {
        (row["query_id"], row["candidate_scene_id"])
        for row in qrels
    }
    require(len(pool_pairs) == len(pool), "Duplicate query-scene pair in pool")
    require(len(qrel_pairs) == len(qrels), "Duplicate query-scene pair in qrels")
    require(pool_pairs == qrel_pairs, "Pool/qrels pair mismatch")
    require(
        len({row["query_id"] for row in qrels}) == scope["queries"],
        "Qrels query coverage mismatch",
    )
    require(
        len({row["candidate_scene_id"] for row in qrels})
        == scope["unique_judged_scenes"],
        "Unique judged scene count mismatch",
    )

    grade_counts = Counter(row["relevance_grade"] for row in qrels)
    require(
        dict(sorted(grade_counts.items())) == judgments["grade_counts"],
        "Relevance grade distribution mismatch",
    )
    leakage_counts = Counter(row["source_leakage"] for row in qrels)
    require(
        dict(sorted(leakage_counts.items())) == judgments["source_leakage_counts"],
        "Source leakage distribution mismatch",
    )
    queries_ge1 = {
        row["query_id"] for row in qrels if int(row["relevance_grade"]) >= 1
    }
    queries_ge2 = {
        row["query_id"] for row in qrels if int(row["relevance_grade"]) >= 2
    }
    require(
        len(queries_ge1) == judgments["queries_with_grade_ge_1"],
        "Grade >=1 query coverage mismatch",
    )
    require(
        len(queries_ge2) == judgments["queries_with_grade_ge_2"],
        "Grade >=2 query coverage mismatch",
    )
    require(
        all(row["review_status"] == "completed" for row in qrels),
        "Incomplete qrels review status",
    )

    run_ranks: dict[str, dict[str, list[int]]] = {
        mode: defaultdict(list) for mode in MODES
    }
    for row in pool:
        ranks = json.loads(row["method_ranks_json"])
        scores = json.loads(row["method_scores_json"])
        methods = set(filter(None, row["source_methods"].split("|")))
        require(methods == set(ranks), "source_methods/method_ranks_json mismatch")
        require(methods == set(scores), "source_methods/method_scores_json mismatch")
        for mode, rank in ranks.items():
            require(mode in MODES, f"Unexpected retrieval mode: {mode}")
            require(
                scores[mode]["effective_mode"] == mode,
                f"Retrieval fallback detected for {mode}/{row['query_id']}",
            )
            run_ranks[mode][row["query_id"]].append(int(rank))

    for mode in MODES:
        total = sum(len(ranks) for ranks in run_ranks[mode].values())
        require(total == scope["results_per_mode"], f"{mode} run depth mismatch")
        require(
            len(run_ranks[mode]) == scope["queries"],
            f"{mode} query coverage mismatch",
        )
        for query_id, ranks in run_ranks[mode].items():
            ordered = sorted(ranks)
            require(
                ordered == list(range(1, len(ordered) + 1)),
                f"Non-contiguous ranks for {mode}/{query_id}",
            )
            require(len(ordered) in {19, 20}, f"Unexpected run depth for {mode}/{query_id}")

    return pool, qrels


def validate_historical_manifests(
    release_root: Path,
    release_manifest: dict[str, Any],
    pool: list[dict[str, str]],
    qrels: list[dict[str, str]],
) -> None:
    manifest_root = release_root / "manifests"
    pool_manifest = read_json(manifest_root / "paper_relevance_pool_run_v1.json")
    require(
        pool_manifest["schema_version"] == "paper-relevance-pool-v1",
        "Unexpected pool manifest schema",
    )
    require(pool_manifest["query_count"] == 100, "Pool manifest query count mismatch")
    require(
        pool_manifest["pooled_pair_count"] == len(pool),
        "Pool manifest pair count mismatch",
    )
    per_query_counts = Counter(row["query_id"] for row in pool)
    require(min(per_query_counts.values()) == pool_manifest["per_query_min"], "Pool min mismatch")
    require(max(per_query_counts.values()) == pool_manifest["per_query_max"], "Pool max mismatch")
    require(
        sum(per_query_counts.values()) / len(per_query_counts)
        == pool_manifest["per_query_mean"],
        "Pool mean mismatch",
    )
    require(pool_manifest["modes"] == list(MODES), "Pool mode order mismatch")
    require(pool_manifest["top_k_per_mode"] == 20, "Pool Top-K mismatch")

    pool_inputs = {
        "queries_sha256": manifest_root / "paper_video_queries_v1.csv",
        "evidence_sha256": manifest_root / "video_evidence_manifest.csv",
        "inventory_sha256": (
            manifest_root / "pool_generation_inputs" / "video_source_inventory.csv"
        ),
    }
    for digest_key, path in pool_inputs.items():
        require(
            sha256_file(path) == pool_manifest["inputs"][digest_key],
            f"Pool input lineage mismatch: {digest_key}",
        )

    frozen_inventory = read_csv(manifest_root / "video_source_inventory.csv")
    pool_inventory = read_csv(
        manifest_root / "pool_generation_inputs" / "video_source_inventory.csv"
    )
    require(
        frozen_inventory == pool_inventory,
        "Dataset-freeze and pool-generation inventories differ semantically",
    )
    require(
        sha256_file(manifest_root / "video_source_inventory.csv")
        != sha256_file(
            manifest_root / "pool_generation_inputs" / "video_source_inventory.csv"
        ),
        "Expected byte-distinct inventory snapshots are not distinct",
    )

    locator = read_json(release_root / "LARGE_ARTIFACT_LOCATOR.json")
    artifacts = locator["artifacts"]
    require(
        artifacts["dense_index"]["sha256"]
        == pool_manifest["inputs"]["dense_index_sha256"],
        "Dense index lineage mismatch",
    )
    require(
        artifacts["visual_index"]["sha256"]
        == pool_manifest["inputs"]["visual_index_sha256"],
        "Visual index lineage mismatch",
    )

    observed_mode_counts: Counter[tuple[str, str]] = Counter()
    for row in pool:
        for mode, score in json.loads(row["method_scores_json"]).items():
            observed_mode_counts[(mode, score["effective_mode"])] += 1
    for requested_mode, effective_counts in pool_manifest[
        "effective_mode_counts"
    ].items():
        for effective_mode, expected_count in effective_counts.items():
            require(
                observed_mode_counts[(requested_mode, effective_mode)]
                == expected_count,
                f"Effective mode count mismatch: {requested_mode}/{effective_mode}",
            )
    require(
        sum(observed_mode_counts.values())
        == sum(
            sum(counts.values())
            for counts in pool_manifest["effective_mode_counts"].values()
        ),
        "Unexpected effective-mode entries in pool",
    )

    qrels_root = manifest_root / "paper_qrels_v1"
    qrels_manifest = read_json(qrels_root / "paper_video_qrels_manifest_v1.json")
    require(qrels_manifest["frozen"] is True, "Qrels manifest is not frozen")
    scope = qrels_manifest["judgment_scope"]
    expected_scope = {
        "queries": release_manifest["scope"]["queries"],
        "query_scene_pairs": release_manifest["scope"]["query_scene_pairs"],
        "unique_scenes": release_manifest["scope"]["unique_judged_scenes"],
        "grade_counts": release_manifest["judgments"]["grade_counts"],
        "source_leakage_counts": release_manifest["judgments"][
            "source_leakage_counts"
        ],
        "queries_with_grade_ge_1": release_manifest["judgments"][
            "queries_with_grade_ge_1"
        ],
        "queries_with_grade_ge_2": release_manifest["judgments"][
            "queries_with_grade_ge_2"
        ],
    }
    require(scope == expected_scope, "Qrels manifest judgment scope mismatch")

    protocol = qrels_manifest["human_review_protocol"]
    for key, value in protocol.items():
        require(
            release_manifest["judgments"].get(key) == value,
            f"Human-review protocol mismatch: {key}",
        )

    review_root = release_root / "review_audit"
    for source in qrels_manifest["source_files"].values():
        path = review_root / source["name"]
        require(path.is_file(), f"Missing review audit source: {source['name']}")
        require(
            sha256_file(path) == source["sha256"],
            f"Review audit source hash mismatch: {source['name']}",
        )

    for output in qrels_manifest["outputs"].values():
        path = qrels_root / output["name"]
        require(path.is_file(), f"Missing qrels output: {output['name']}")
        require(
            sha256_file(path) == output["sha256"],
            f"Qrels output hash mismatch: {output['name']}",
        )

    expected_graded = {
        (row["query_id"], row["candidate_scene_id"]): int(row["relevance_grade"])
        for row in qrels
    }
    expected_binary = {
        key: int(grade >= 2) for key, grade in expected_graded.items()
    }
    require(
        read_trec_qrels(qrels_root / "paper_video_qrels_graded_v1.txt")
        == expected_graded,
        "Graded TREC qrels differ from audit CSV",
    )
    require(
        read_trec_qrels(qrels_root / "paper_video_qrels_binary_ge2_v1.txt")
        == expected_binary,
        "Binary TREC qrels differ from audit CSV",
    )


def validate_frozen_results(release_root: Path, manifest: dict[str, Any]) -> None:
    result_root = release_root / "results" / "paper_retrieval_eval_v1"
    summary = read_csv(result_root / "paper_retrieval_metrics_summary_v1.csv")
    target = manifest["frozen_primary_result"]
    rows = [
        row
        for row in summary
        if row["mode"] == target["mode"] and int(row["cutoff"]) == target["cutoff"]
    ]
    require(len(rows) == 1, "Frozen primary result row is missing")
    row = rows[0]
    for metric in ("ndcg", "map", "mrr", "recall", "precision"):
        require(row[metric] == target[metric], f"Frozen {metric} mismatch")

    evaluation = read_json(result_root / "paper_retrieval_evaluation_v1.json")
    require(evaluation["total_queries"] == manifest["scope"]["queries"], "Result query count mismatch")
    require(
        evaluation["queries_with_grade_ge_2"]
        == manifest["judgments"]["queries_with_grade_ge_2"],
        "Result binary-evaluable query count mismatch",
    )


def replay_evaluation(release_root: Path) -> None:
    result_root = release_root / "results" / "paper_retrieval_eval_v1"
    manifest_root = release_root / "manifests"
    evaluator = PROJECT_ROOT / "evaluate_paper_video_retrieval.py"
    require(evaluator.is_file(), "evaluate_paper_video_retrieval.py is missing")

    with tempfile.TemporaryDirectory(prefix="paper_retrieval_replay_") as temp:
        output_dir = Path(temp)
        command = [
            sys.executable,
            str(evaluator),
            "--pool",
            str(manifest_root / "paper_relevance_pool_audit_v1.csv"),
            "--qrels",
            str(
                manifest_root
                / "paper_qrels_v1"
                / "paper_video_qrels_graded_v1.csv"
            ),
            "--qrels-manifest",
            str(
                manifest_root
                / "paper_qrels_v1"
                / "paper_video_qrels_manifest_v1.json"
            ),
            "--pool-manifest",
            str(manifest_root / "paper_relevance_pool_run_v1.json"),
            "--output-dir",
            str(output_dir),
        ]
        subprocess.run(command, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True)

        for name in REPLAY_RESULT_FILES:
            require(
                sha256_file(output_dir / name) == sha256_file(result_root / name),
                f"Replay output differs: {name}",
            )

        frozen = read_json(result_root / "paper_retrieval_evaluation_v1.json")
        replayed = read_json(output_dir / "paper_retrieval_evaluation_v1.json")
        for key in (
            "modes",
            "cutoffs",
            "primary_binary_threshold",
            "graded_gain",
            "top_k_run_depth",
            "pool_relative_metrics",
            "total_queries",
            "queries_with_grade_ge_2",
            "run_depth",
            "summary",
            "paired_bootstrap",
        ):
            require(frozen[key] == replayed[key], f"Replay JSON differs at {key}")


def main() -> None:
    args = parse_args()
    release_root = args.release_root.resolve()
    manifest_path = release_root / "RELEASE_MANIFEST.json"
    require(manifest_path.is_file(), f"Release manifest not found: {manifest_path}")
    manifest = read_json(manifest_path)
    require(manifest.get("frozen") is True, "Release is not marked frozen")

    validate_payloads(release_root, manifest)
    validate_dataset_manifests(release_root, manifest["scope"])
    pool, qrels = validate_pool_and_qrels(release_root, manifest)
    validate_historical_manifests(release_root, manifest, pool, qrels)
    validate_frozen_results(release_root, manifest)
    if args.replay:
        replay_evaluation(release_root)

    print(
        "paper_retrieval_release_check=OK "
        f"release={manifest['release_id']} replay={'yes' if args.replay else 'no'}"
    )


if __name__ == "__main__":
    main()
