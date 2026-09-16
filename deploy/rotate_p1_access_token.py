"""Rotate the P1 bearer token without printing it to stdout."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from dotenv import set_key


def main() -> None:
    env_path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    output_path = Path(
        sys.argv[2] if len(sys.argv) > 2 else "/tmp/rag3d_p1_access_token.txt"
    )
    token = secrets.token_urlsafe(48)
    set_key(env_path, "KAFU_API_TOKEN", token, quote_mode="never")
    output_path.write_text(f"KAFU_API_TOKEN={token}\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    os.chmod(output_path, 0o600)
    print(f"token_rotated output={output_path}")


if __name__ == "__main__":
    main()
