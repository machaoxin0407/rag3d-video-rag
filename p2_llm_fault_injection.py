#!/usr/bin/env python3
"""Isolated LLM/VLM outage checks without mutating the running deployment."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import api_server
from video_rag.diagnosis import _vision_diagnosis


ROOT = Path(__file__).resolve().parent


def main() -> None:
    results = []
    with patch.dict(
        os.environ,
        {
            "USER_VIDEO_VLM_BASE_URL": "",
            "USER_VIDEO_VLM_API_KEY": "",
            "USER_VIDEO_VLM_MODEL": "",
        },
    ):
        diagnosis, model = _vision_diagnosis(
            [],
            question="Is this operation safe?",
            product_class="Air Fryer",
            standard_context="",
        )
    results.append(
        {
            "fault": "diagnosis_vlm_unconfigured",
            "passed": diagnosis["label"] == "insufficient_evidence"
            and model.get("fallback") == "vlm_not_configured",
            "observed": diagnosis["label"],
            "expected": "insufficient_evidence safe degradation",
        }
    )

    with patch.object(api_server, "EXPECTED_TOKEN", "p2-test-token"):
        client = TestClient(api_server.app, raise_server_exceptions=False)
        with patch.object(
            api_server,
            "_run_agent_sync",
            side_effect=RuntimeError("injected answer provider outage"),
        ):
            response = client.post(
                "/v2/chat",
                headers={"Authorization": "Bearer p2-test-token"},
                json={"question": "How do I use an air fryer?", "images": []},
            )
    results.append(
        {
            "fault": "answer_llm_provider_outage",
            "passed": response.status_code == 500
            and "injected answer provider outage" not in response.text,
            "observed": response.status_code,
            "expected": "HTTP 500 without provider detail or fabricated answer",
        }
    )
    report = {
        "experiment_id": "FAULT-LLM-20260729-001",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "isolation": "in-process controlled mock; no deployment mutation",
        "results": results,
        "passed": all(item["passed"] for item in results),
        "limitation": (
            "The answer path fails closed with an explicit generic 500 rather than "
            "returning a degraded grounded answer; product retry UX remains future work."
        ),
    }
    output = ROOT / "reports" / "p2" / "online" / "llm_fault_injection.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
