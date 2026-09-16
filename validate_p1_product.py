"""Fast, deterministic P1 release gate for local and server execution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIRED = [
    "Dockerfile",
    "compose.yaml",
    "compose.server.yaml",
    "p1_stack.sh",
    "video_job_worker.py",
    "video_rag/diagnosis.py",
    "web_demo/index.html",
    "docs/P1_DEPLOYMENT_RUNBOOK.md",
    "docs/P1_COMPLETION_AND_ACCEPTANCE_2026-07-29.md",
    "validation_outputs/p1_online_100_report.json",
    "deploy/nginx.p1.conf.example",
    "deploy/rotate_p1_access_token.py",
    "deploy/import_authorized_model_config.py",
    "deploy/probe_model_config.py",
    "deploy/server_p1_smoke.py",
    "validate_p1_online_retrieval.py",
]


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        print(json.dumps({"status": "failed", "missing": missing}, ensure_ascii=False))
        return 1
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.test_p1_product", "-v"],
        cwd=ROOT,
        text=True,
    )
    report = {
        "status": "passed" if completed.returncode == 0 else "failed",
        "required_artifacts": len(REQUIRED),
        "tests": "tests.test_p1_product",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
