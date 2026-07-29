"""Import only approved model settings into the P1 private .env without outputting keys."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key


def main() -> None:
    source = dotenv_values(sys.argv[1])
    target = Path(sys.argv[2] if len(sys.argv) > 2 else ".env")
    key = source.get("NEWPULSE_MODEL_API_KEY") or source.get("DASHSCOPE_API_KEY")
    base = source.get("NEWPULSE_MODEL_BASE_URL")
    model = source.get("NEWPULSE_MODEL_NAME")
    if not (key and base and model):
        raise SystemExit("source model configuration is incomplete")
    assignments = {
        "SILICONFLOW_BASE_URL": base,
        "SILICONFLOW_API_KEY": key,
        "SILICONFLOW_MODEL": model,
        "USER_VIDEO_VLM_BASE_URL": base,
        "USER_VIDEO_VLM_API_KEY": key,
        "USER_VIDEO_VLM_MODEL": model,
    }
    for name, value in assignments.items():
        set_key(target, name, str(value), quote_mode="never")
    os.chmod(target, 0o600)
    print("authorized_model_config_imported=true")


if __name__ == "__main__":
    main()
