#!/usr/bin/env python3
"""Resumable authenticated 24-hour health and chat soak test."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--output", type=Path, default=Path("reports/p2/online/soak_24h.jsonl")
    )
    args = parser.parse_args()
    load_dotenv()
    headers = {"Authorization": f"Bearer {os.environ['KAFU_API_TOKEN']}"}
    deadline = time.monotonic() + args.hours * 3600
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        while time.monotonic() < deadline:
            started = time.monotonic()
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "health_ok": False,
                "chat_ok": False,
            }
            try:
                health = requests.get(f"{args.base_url}/health", timeout=15)
                record["health_ok"] = health.status_code == 200
                chat = requests.post(
                    f"{args.base_url}/v2/chat",
                    headers=headers,
                    json={
                        "question": "How do I set an air fryer cooking time?",
                        "images": [],
                    },
                    timeout=180,
                )
                record["chat_ok"] = chat.status_code == 200
                record["latency_seconds"] = time.monotonic() - started
            except Exception as exc:
                record["error_type"] = type(exc).__name__
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            remaining = args.interval_seconds - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)


if __name__ == "__main__":
    main()
