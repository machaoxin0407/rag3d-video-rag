"""Verify all 100 frozen paper queries execute through strict online Tri-Hybrid."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from video_rag.retrieval import VideoEvidenceRetriever


ROOT = Path(__file__).resolve().parent
QUERY_PATH = ROOT / "data_video" / "manifests" / "paper_video_queries_v1.csv"
REPORT_PATH = ROOT / "validation_outputs" / "p1_online_100_report.json"


def main() -> None:
    with QUERY_PATH.open("r", encoding="utf-8-sig", newline="") as stream:
        queries = list(csv.DictReader(stream))
    if len(queries) != 100:
        raise RuntimeError(f"expected 100 frozen queries, found {len(queries)}")
    retriever = VideoEvidenceRetriever(mode="tri_hybrid")
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    for query in queries:
        results = retriever.search(query["query_text"], top_k=10, strict=True)
        modes = sorted({result.retrieval_mode for result in results})
        passed = bool(results) and modes == ["tri_hybrid"]
        if not passed:
            failures.append(query["query_id"])
        rows.append(
            {
                "query_id": query["query_id"],
                "results": len(results),
                "modes": modes,
                "passed": passed,
            }
        )
    report = {
        "status": "passed" if not failures else "failed",
        "queries": len(rows),
        "strict_tri_hybrid_queries": len(rows) - len(failures),
        "failures": failures,
        "rows": rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {key: report[key] for key in ("status", "queries", "strict_tri_hybrid_queries", "failures")},
            ensure_ascii=False,
            indent=2,
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
