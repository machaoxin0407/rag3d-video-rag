#!/usr/bin/env python3
"""Benchmark retrieval and inject isolated dense/visual endpoint failures."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from video_rag.retrieval import VideoEvidenceRetriever


ROOT = Path(__file__).resolve().parent
MODES = ("bm25", "dense", "visual", "hybrid", "tri_hybrid")
QUERY = "How do I set the cooking temperature and time on an air fryer?"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def timed_search(
    retriever: VideoEvidenceRetriever, mode: str
) -> tuple[float, str | None]:
    started = time.perf_counter()
    results = retriever.search(QUERY, top_k=5, mode=mode, strict=True)
    return (
        (time.perf_counter() - started) * 1000,
        results[0].retrieval_mode if results else None,
    )


def main() -> None:
    output = ROOT / "reports" / "p2" / "online"
    output.mkdir(parents=True, exist_ok=True)
    init_started = time.perf_counter()
    retriever = VideoEvidenceRetriever(mode="tri_hybrid")
    init_ms = (time.perf_counter() - init_started) * 1000
    rows: list[dict[str, Any]] = []
    for mode in MODES:
        timings: list[float] = []
        effective: str | None = None
        for _ in range(22):
            latency, effective = timed_search(retriever, mode)
            timings.append(latency)
        measured = timings[2:]
        rows.append(
            {
                "mode": mode,
                "concurrency": 1,
                "requests": len(measured),
                "failures": 0,
                "cold_first_query_ms": f"{timings[0]:.6f}",
                "p50_ms": f"{median(measured):.6f}",
                "p95_ms": f"{percentile(measured, .95):.6f}",
                "p99_ms": f"{percentile(measured, .99):.6f}",
                "effective_mode": effective,
            }
        )
    for concurrency in (2, 4, 8):
        timings: list[float] = []
        failures = 0
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(timed_search, retriever, "tri_hybrid")
                for _ in range(concurrency * 3)
            ]
            for future in as_completed(futures):
                try:
                    latency, _ = future.result()
                    timings.append(latency)
                except Exception:
                    failures += 1
        rows.append(
            {
                "mode": "tri_hybrid",
                "concurrency": concurrency,
                "requests": concurrency * 3,
                "failures": failures,
                "cold_first_query_ms": "",
                "p50_ms": f"{median(timings):.6f}" if timings else "",
                "p95_ms": f"{percentile(timings, .95):.6f}" if timings else "",
                "p99_ms": f"{percentile(timings, .99):.6f}" if timings else "",
                "effective_mode": "tri_hybrid" if not failures else "mixed",
            }
        )
    with (output / "retrieval_latency.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    original_dense = os.getenv("VIDEO_DENSE_ENDPOINT")
    original_visual = os.getenv("VIDEO_VISUAL_DENSE_ENDPOINT")
    faults: list[dict[str, Any]] = []
    try:
        os.environ["VIDEO_DENSE_ENDPOINT"] = "http://127.0.0.1:1"
        os.environ["VIDEO_VISUAL_DENSE_ENDPOINT"] = "http://127.0.0.1:2"
        isolated = VideoEvidenceRetriever(mode="tri_hybrid")
        try:
            isolated.search(QUERY, top_k=3, mode="tri_hybrid", strict=True)
            strict_rejected = False
        except RuntimeError:
            strict_rejected = True
        fallback = isolated.search(
            QUERY, top_k=3, mode="tri_hybrid", strict=False
        )
        faults.extend(
            [
                {
                    "fault": "dense_and_visual_unreachable_strict",
                    "passed": strict_rejected,
                    "observed": "RuntimeError" if strict_rejected else "no error",
                    "expected": "RuntimeError; no silent production fallback",
                },
                {
                    "fault": "dense_and_visual_unreachable_nonstrict",
                    "passed": bool(fallback)
                    and fallback[0].retrieval_mode == "bm25",
                    "observed": fallback[0].retrieval_mode if fallback else "empty",
                    "expected": "explicit bm25 fallback",
                },
            ]
        )
    finally:
        if original_dense is None:
            os.environ.pop("VIDEO_DENSE_ENDPOINT", None)
        else:
            os.environ["VIDEO_DENSE_ENDPOINT"] = original_dense
        if original_visual is None:
            os.environ.pop("VIDEO_VISUAL_DENSE_ENDPOINT", None)
        else:
            os.environ["VIDEO_VISUAL_DENSE_ENDPOINT"] = original_visual

    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip().splitlines()
    memory = subprocess.run(
        ["free", "-b"], capture_output=True, text=True, check=False
    ).stdout
    cpu = subprocess.run(
        ["sh", "-c", "uptime && nproc"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    report = {
        "experiment_id": "RET-PERF-20260729-001",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retriever_initialization_ms": init_ms,
        "latency_table": "retrieval_latency.csv",
        "isolated_fault_injection": faults,
        "gpu_snapshot": gpu,
        "memory_snapshot": memory,
        "cpu_snapshot": cpu,
        "target_p95_ms": 1000,
    }
    (output / "retrieval_performance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
