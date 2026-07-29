"""Probe an authorized model .env without printing any credential value."""

from __future__ import annotations

import sys
from urllib.parse import urlparse

import requests
from dotenv import dotenv_values


def main() -> None:
    values = {key: str(value or "").strip() for key, value in dotenv_values(sys.argv[1]).items()}
    base = values.get("OPENAI_BASE_URL") or values.get("API_BASE_URL") or values.get("NEWPULSE_MODEL_BASE_URL")
    key = (
        values.get("OPENAI_API_KEY")
        or values.get("API_KEY")
        or values.get("NEWPULSE_MODEL_API_KEY")
        or values.get("DASHSCOPE_API_KEY")
    )
    model = values.get("OPENAI_MODEL") or values.get("API_CHAT_MODEL") or values.get("NEWPULSE_MODEL_NAME")
    if not (base and key and model):
        print("configured=false")
        return
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    response = requests.post(
        f"{base.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": model.split("#", 1)[0].strip(),
            "messages": [{"role": "user", "content": "Reply only OK"}],
            "max_tokens": 4,
        },
        timeout=30,
    )
    print(
        f"host={urlparse(base).netloc or urlparse(base).path} "
        f"model={model.split('#', 1)[0].strip()} status={response.status_code}"
    )


if __name__ == "__main__":
    main()
