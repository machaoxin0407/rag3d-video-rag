#!/usr/bin/env python3
"""Run P2 end-to-end, diagnostic, concurrency, and fault-injection checks.

This program is intended for the authorized deployment server. It never prints
or persists credentials. Raw model judgments are retained for auditability.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import requests
from dotenv import load_dotenv
from openai import OpenAI

from video_rag.diagnosis import extract_keyframes, ffmpeg_executable, probe_video


ROOT = Path(__file__).resolve().parent
SEED = 20260729
JUDGE_PROMPT_VERSION = "p2-answer-judge-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"empty output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def public_model_config() -> tuple[str, str, str]:
    base = (
        os.getenv("P2_JUDGE_BASE_URL")
        or os.getenv("SILICONFLOW_BASE_URL")
        or os.getenv("API_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or ""
    ).strip()
    key = (
        os.getenv("P2_JUDGE_API_KEY")
        or os.getenv("SILICONFLOW_API_KEY")
        or os.getenv("API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    model = (
        os.getenv("P2_JUDGE_MODEL")
        or os.getenv("SILICONFLOW_MODEL")
        or os.getenv("API_CHAT_MODEL")
        or os.getenv("OPENAI_MODEL")
        or ""
    ).strip()
    if not (base and key and model):
        raise RuntimeError("P2 judge model is not configured")
    return base, key, model


def fetch_media(base: str, headers: dict[str, str], path: str) -> bool:
    with requests.get(
        f"{base}{path}",
        headers={**headers, "Range": "bytes=0-1023"},
        timeout=30,
        stream=True,
    ) as response:
        response.raise_for_status()
        return bool(next(response.iter_content(1024), b""))


def chat_once(
    base: str, headers: dict[str, str], query: dict[str, str]
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    response = requests.post(
        f"{base}/v2/chat",
        headers=headers,
        json={"question": query["query_text"], "images": []},
        timeout=180,
    )
    latency = time.monotonic() - started
    response.raise_for_status()
    return response.json()["data"], latency


def judge_answer(
    client: OpenAI,
    model: str,
    query: dict[str, str],
    chat: dict[str, Any],
    relevant_notes: list[str],
    no_positive: bool,
) -> tuple[dict[str, Any], str]:
    evidence = [
        {
            "type": citation.get("evidence_type"),
            "source_id": citation.get("source_id"),
            "excerpt": citation.get("excerpt", "")[:500],
        }
        for citation in chat.get("citations", [])
    ]
    prompt = {
        "instruction": (
            "Evaluate only against the supplied evidence. Return strict JSON with "
            "scores in [0,1]: correctness, evidence_support, video_support, "
            "non_hallucination, safety_handling, no_answer_handling; plus "
            "failure_reasons (array). A no-positive query means the judged video "
            "pool has no direct demonstration, not that manuals cannot answer it. "
            "Do not reward unsupported specificity."
        ),
        "query": query,
        "answer": chat.get("answer", ""),
        "structured_evidence": evidence,
        "human_relevance_notes": relevant_notes[:8],
        "video_pool_has_direct_answer": not no_positive,
    }
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        extra_body={"enable_thinking": False},
        messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
    )
    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    required = {
        "correctness",
        "evidence_support",
        "video_support",
        "non_hallucination",
        "safety_handling",
        "no_answer_handling",
        "failure_reasons",
    }
    if not required.issubset(parsed):
        raise ValueError("judge output missing required fields")
    for field in required - {"failure_reasons"}:
        parsed[field] = max(0.0, min(1.0, float(parsed[field])))
    if not isinstance(parsed["failure_reasons"], list):
        raise ValueError("judge failure_reasons is not a list")
    return parsed, raw


def run_end_to_end(
    base: str,
    headers: dict[str, str],
    output: Path,
    limit: int,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], list[float]]:
    release = ROOT / "data_video" / "releases" / "paper_video_retrieval_v1"
    all_queries = read_csv(
        release / "manifests" / "paper_video_queries_v1.csv"
    )
    queries = all_queries[offset : offset + limit]
    qrels = read_csv(
        ROOT
        / "data_video"
        / "manifests"
        / "paper_qrels_v2"
        / "paper_video_qrels_graded_v2.csv"
    )
    qrels_by_query: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in qrels:
        qrels_by_query[row["query_id"]].append(row)
    judge_base, judge_key, judge_model = public_model_config()
    client = OpenAI(base_url=judge_base, api_key=judge_key, timeout=120, max_retries=1)
    rows: list[dict[str, Any]] = []
    raw_path = output / "answer_judge_raw.jsonl"
    output.mkdir(parents=True, exist_ok=True)
    latencies: list[float] = []
    with raw_path.open("w", encoding="utf-8") as raw_stream:
        for index, query in enumerate(queries, 1):
            chat, latency = chat_once(base, headers, query)
            latencies.append(latency)
            videos = chat.get("videos", [])
            citations = chat.get("citations", [])
            images = chat.get("manual_images", [])
            media_urls = [
                *(video["clip_url"] for video in videos),
                *(video["thumbnail_url"] for video in videos),
                *(image["url"] for image in images),
            ]
            media_ok = [fetch_media(base, headers, path) for path in media_urls]
            valid_video_intervals = all(
                float(video["end_seconds"]) > float(video["start_seconds"]) >= 0
                for video in videos
            )
            video_ids = {video["scene_id"] for video in videos}
            video_citations = {
                citation["source_id"]
                for citation in citations
                if citation["evidence_type"] == "video_scene"
            }
            direct_rows = [
                row
                for row in qrels_by_query[query["query_id"]]
                if row["primary_eval_eligible"] == "yes"
                and int(row["relevance_grade"]) >= 2
            ]
            relevant_notes = [
                row["evidence_notes"] for row in direct_rows if row["evidence_notes"]
            ]
            judge, raw = judge_answer(
                client,
                judge_model,
                query,
                chat,
                relevant_notes,
                no_positive=not direct_rows,
            )
            human_review_required = (
                query["query_type"] == "safety"
                or any(
                    judge[field] < 0.5
                    for field in (
                        "correctness",
                        "evidence_support",
                        "non_hallucination",
                        "safety_handling",
                    )
                )
                or bool(judge["failure_reasons"])
            )
            row = {
                "query_id": query["query_id"],
                "split": query["split"],
                "product_class": query["product_class"],
                "query_type": query["query_type"],
                "latency_seconds": f"{latency:.6f}",
                "answer_nonempty": int(bool(chat.get("answer", "").strip())),
                "requested_mode": (chat.get("retrieval") or {}).get("requested_mode", ""),
                "effective_mode": (chat.get("retrieval") or {}).get("effective_mode", ""),
                "video_count": len(videos),
                "citation_count": len(citations),
                "manual_image_count": len(images),
                "all_media_valid": int(all(media_ok) if media_ok else True),
                "video_intervals_valid": int(valid_video_intervals),
                "video_citations_resolve": int(video_citations.issubset(video_ids)),
                "pool_has_direct_video_answer": int(bool(direct_rows)),
                **{
                    f"judge_{key}": f"{value:.6f}"
                    for key, value in judge.items()
                    if key != "failure_reasons"
                },
                "judge_failure_reasons": json.dumps(
                    judge["failure_reasons"], ensure_ascii=False
                ),
                "human_review_required": int(human_review_required),
            }
            rows.append(row)
            raw_stream.write(
                json.dumps(
                    {
                        "query_id": query["query_id"],
                        "judge_model": judge_model,
                        "prompt_version": JUDGE_PROMPT_VERSION,
                        "raw_output": raw,
                        "structured_input": {
                            "question": query["query_text"],
                            "answer": chat.get("answer", ""),
                            "citations": citations,
                            "videos": videos,
                            "manual_images": images,
                            "relevant_notes": relevant_notes,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            print(f"e2e={index}/{len(queries)} query={query['query_id']}", flush=True)
    write_csv(output / "end_to_end_per_query.csv", rows)
    metric_fields = [
        "answer_nonempty",
        "all_media_valid",
        "video_intervals_valid",
        "video_citations_resolve",
        "judge_correctness",
        "judge_evidence_support",
        "judge_video_support",
        "judge_non_hallucination",
        "judge_safety_handling",
        "judge_no_answer_handling",
    ]
    summary = {
        "experiment_id": "ANS-20260729-001",
        "created_at": utc_now(),
        "queries": len(rows),
        "judge": {"model": judge_model, "prompt_version": JUDGE_PROMPT_VERSION},
        "metrics": {
            field: mean(float(row[field]) for row in rows) for field in metric_fields
        },
        "human_review_queue": sum(int(row["human_review_required"]) for row in rows),
        "latency_seconds": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
        },
        "limitations": (
            "AI judge scores are provisional. One human must review the generated "
            "failure/high-risk queue before paper claims are finalized."
        ),
    }
    (output / "end_to_end_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return rows, latencies


def poll_job(
    base: str, headers: dict[str, str], job_id: str, timeout: int = 240
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = requests.get(
            f"{base}/v2/video-jobs/{job_id}", headers=headers, timeout=15
        )
        response.raise_for_status()
        state = response.json()
        if state["status"] in {"completed", "failed"}:
            result = requests.get(
                f"{base}/v2/video-jobs/{job_id}/result",
                headers=headers,
                timeout=15,
            )
            if result.status_code == 200:
                return result.json()
            return state
        time.sleep(1)
    raise TimeoutError(job_id)


def submit_video(
    base: str,
    headers: dict[str, str],
    path: Path,
    product: str,
    question: str,
) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    with path.open("rb") as stream:
        response = requests.post(
            f"{base}/v2/video-jobs",
            headers=headers,
            files={"video": (path.name, stream, "video/mp4")},
            data={"product_class": product, "question": question},
            timeout=30,
        )
    response.raise_for_status()
    job_id = response.json()["job_id"]
    result = poll_job(base, headers, job_id)
    requests.delete(
        f"{base}/v2/video-jobs/{job_id}", headers=headers, timeout=15
    ).raise_for_status()
    return result, time.monotonic() - started


def run_diagnosis(
    base: str, headers: dict[str, str], output: Path
) -> list[dict[str, Any]]:
    evidence = read_csv(ROOT / "data_video" / "manifests" / "video_evidence_manifest.csv")
    inventory = {
        row["record_id"]: row
        for row in read_csv(
            ROOT / "data_video" / "manifests" / "video_source_inventory.csv"
        )
    }
    chosen: dict[str, dict[str, str]] = {}
    for row in evidence:
        if row.get("evidence_type") != "video_scene":
            continue
        product = inventory[row["record_id"]]["product_class"]
        path = ROOT / row["media_path"]
        eligible_product = product in {
            "Air Fryer",
            "Espresso Machine",
            "Pressure Cooker",
            "Printer",
            "Vacuum",
            "Washing Machine",
        }
        if eligible_product and product not in chosen and path.is_file():
            try:
                media = probe_video(path)
                with tempfile.TemporaryDirectory() as validation_dir:
                    extract_keyframes(
                        path,
                        Path(validation_dir),
                        duration_seconds=float(media["duration_seconds"]),
                    )
            except (
                OSError,
                ValueError,
                RuntimeError,
                subprocess.SubprocessError,
            ):
                continue
            if 2.0 <= float(media["duration_seconds"]) <= 60.0:
                chosen[product] = row
    if len(chosen) != 6:
        raise RuntimeError(f"diagnostic source coverage is {len(chosen)}/6 products")
    products = sorted(chosen)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as temp:
        black = Path(temp) / "occluded.mp4"
        subprocess.run(
            [
                ffmpeg_executable(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=320x240:d=3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(black),
            ],
            check=True,
            timeout=30,
        )
        cases: list[tuple[str, str, Path, str, str, str]] = []
        for index, product in enumerate(products):
            own = ROOT / chosen[product]["media_path"]
            other_product = products[(index + 1) % len(products)]
            other = ROOT / chosen[other_product]["media_path"]
            cases.extend(
                [
                    (
                        f"DIAG-{index+1:02d}-A",
                        "correct_step",
                        own,
                        product,
                        f"Is the shown {product} operation consistent with the standard evidence?",
                        "natural accepted standard scene; proxy positive",
                    ),
                    (
                        f"DIAG-{index+1:02d}-B",
                        "insufficient_evidence",
                        black,
                        product,
                        f"Is this {product} operation correct?",
                        "synthetic full occlusion",
                    ),
                    (
                        f"DIAG-{index+1:02d}-C",
                        "out_of_scope",
                        other,
                        product,
                        f"Is this {product} operation correct?",
                        f"cross-product substitution from {other_product}",
                    ),
                ]
            )
        for index, (case_id, label, path, product, question, transform) in enumerate(cases, 1):
            result, latency = submit_video(base, headers, path, product, question)
            diagnosis = (result.get("result") or {}).get("diagnosis", {})
            predicted = diagnosis.get("label", "failed")
            rows.append(
                {
                    "case_id": case_id,
                    "gold_label": label,
                    "predicted_label": predicted,
                    "correct": int(predicted == label),
                    "product_class": product,
                    "synthetic": int(label != "correct_step"),
                    "transformation": transform,
                    "latency_seconds": f"{latency:.6f}",
                    "confidence": diagnosis.get("confidence", ""),
                    "job_status": result.get("status", ""),
                    "model": ((result.get("result") or {}).get("model") or {}).get("model", ""),
                }
            )
            print(f"diagnosis={index}/{len(cases)} case={case_id}", flush=True)
    labels = sorted({row["gold_label"] for row in rows})
    f1s: list[float] = []
    for label in labels:
        tp = sum(row["gold_label"] == label and row["predicted_label"] == label for row in rows)
        fp = sum(row["gold_label"] != label and row["predicted_label"] == label for row in rows)
        fn = sum(row["gold_label"] == label and row["predicted_label"] != label for row in rows)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    summary = {
        "experiment_id": "DIAG-20260729-001",
        "created_at": utc_now(),
        "cases": len(rows),
        "labels_evaluated": labels,
        "macro_f1": mean(f1s),
        "accuracy": mean(row["correct"] for row in rows),
        "failed_jobs": sum(row["job_status"] != "completed" for row in rows),
        "target_macro_f1": 0.70,
        "product_status": "validated_mvp" if mean(f1s) >= 0.70 else "experimental_only",
        "limitations": (
            "Controlled proxy benchmark: positives are accepted standard scenes; "
            "negative cases are synthetic occlusion and cross-product substitution. "
            "It does not represent natural user errors."
        ),
    }
    write_csv(output / "diagnosis_per_case.csv", rows)
    (output / "diagnosis_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return rows


def run_performance_and_faults(
    base: str,
    headers: dict[str, str],
    output: Path,
    e2e_latencies: list[float],
) -> None:
    query = {
        "query_text": "How do I set the cooking temperature and time on an air fryer?"
    }
    concurrency_rows: list[dict[str, Any]] = []
    standalone_latencies: list[float] = []
    for concurrency in (1, 2, 4, 8):
        started = time.monotonic()
        latencies: list[float] = []
        failures = 0
        requests_at_level = 5 if concurrency == 1 else concurrency
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [
                pool.submit(chat_once, base, headers, query)
                for _ in range(requests_at_level)
            ]
            for future in as_completed(futures):
                try:
                    _, latency = future.result()
                    latencies.append(latency)
                except Exception:
                    failures += 1
        concurrency_rows.append(
            {
                "concurrency": concurrency,
                "requests": requests_at_level,
                "failures": failures,
                "wall_seconds": f"{time.monotonic() - started:.6f}",
                "p50_seconds": f"{percentile(latencies, .5):.6f}",
                "p95_seconds": f"{percentile(latencies, .95):.6f}",
                "p99_seconds": f"{percentile(latencies, .99):.6f}",
            }
        )
        if concurrency == 1:
            standalone_latencies = latencies
    write_csv(output / "chat_concurrency.csv", concurrency_rows)
    faults: list[dict[str, Any]] = []
    for name, fault_headers, expected in (
        ("missing_auth", {}, 401),
        ("invalid_auth", {"Authorization": "Bearer invalid"}, 401),
    ):
        response = requests.post(
            f"{base}/v2/chat",
            headers=fault_headers,
            json={"question": query["query_text"], "images": []},
            timeout=30,
        )
        faults.append(
            {
                "fault": name,
                "observed_status": response.status_code,
                "expected_status": expected,
                "passed": int(response.status_code == expected),
            }
        )
    with tempfile.NamedTemporaryFile(suffix=".mp4") as invalid:
        invalid.write(b"not a video")
        invalid.flush()
        with open(invalid.name, "rb") as stream:
            response = requests.post(
                f"{base}/v2/video-jobs",
                headers=headers,
                files={"video": ("invalid.mp4", stream, "video/mp4")},
                data={"product_class": "Air Fryer", "question": "test"},
                timeout=30,
            )
        passed = response.status_code in {400, 415, 422}
        if response.status_code == 202:
            state = poll_job(base, headers, response.json()["job_id"])
            passed = state.get("status") == "failed"
            requests.delete(
                f"{base}/v2/video-jobs/{response.json()['job_id']}",
                headers=headers,
                timeout=15,
            )
        faults.append(
            {
                "fault": "invalid_video",
                "observed_status": response.status_code,
                "expected_status": "4xx or asynchronous failed",
                "passed": int(passed),
            }
        )
    write_csv(output / "fault_injection.csv", faults)
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
    summary = {
        "experiment_id": "PERF-20260729-001",
        "created_at": utc_now(),
        "formal_e2e_requests": len(e2e_latencies),
        "formal_e2e_workload_latency_seconds": {
            "p50": percentile(e2e_latencies, 0.50),
            "p95": percentile(e2e_latencies, 0.95),
            "p99": percentile(e2e_latencies, 0.99),
            "note": "formal run used four non-overlapping concurrent shards",
        },
        "sequential_e2e_requests": len(standalone_latencies),
        "sequential_e2e_latency_seconds": {
            "p50": percentile(standalone_latencies, 0.50),
            "p95": percentile(standalone_latencies, 0.95),
            "p99": percentile(standalone_latencies, 0.99),
        },
        "gpu_snapshot": gpu,
        "concurrency_levels": [1, 2, 4, 8],
        "faults_passed": sum(row["passed"] for row in faults),
        "faults_total": len(faults),
        "cold_start": {
            "status": "not_measured",
            "reason": "services were already warm after the formal end-to-end run",
        },
        "warm_latency": "five repeated single-user requests plus concurrency 2/4/8",
        "24_hour_soak": {
            "status": "not_run",
            "reason": (
                "A real 24-hour wall-clock run cannot be represented by an immediate "
                "P2 execution. The resumable command is documented separately."
            ),
        },
    }
    (output / "performance_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "p2" / "online")
    parser.add_argument("--skip-diagnosis", action="store_true")
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument(
        "--skip-e2e",
        action="store_true",
        help="Reuse an already merged end_to_end_per_query.csv in output-dir.",
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    token = os.environ["KAFU_API_TOKEN"]
    headers = {"Authorization": f"Bearer {token}"}
    health = requests.get(f"{args.base_url}/health", timeout=15).json()
    if health.get("status") != "ok":
        raise RuntimeError("API health is not ok")
    video_health = health.get("video_retrieval") or {}
    if not video_health.get("exact_ready"):
        raise RuntimeError("strict Tri-Hybrid is not ready")
    output = args.output_dir.resolve()
    if args.skip_e2e:
        existing = read_csv(output / "end_to_end_per_query.csv")
        rows = existing
        latencies = [float(row["latency_seconds"]) for row in existing]
    else:
        rows, latencies = run_end_to_end(
            args.base_url,
            headers,
            output,
            min(100, max(1, args.limit)),
            max(0, args.offset),
        )
    if not args.skip_diagnosis:
        run_diagnosis(args.base_url, headers, output)
    if not args.skip_performance:
        run_performance_and_faults(args.base_url, headers, output, latencies)
    manifest = {
        "schema_version": "p2-online-evaluation-v1",
        "created_at": utc_now(),
        "queries_completed": len(rows),
        "query_offset": max(0, args.offset),
        "strict_tri_hybrid_ready": True,
        "credentials_persisted": False,
        "output_dir": str(output),
    }
    (output / "online_run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
