#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
# The server account has no sudo and Ubuntu's python3-venv package is absent.
# User-space virtualenv is already available and keeps this stage isolated.
python3 -m virtualenv --clear .venv-vlm
.venv-vlm/bin/python -m pip install --upgrade pip
.venv-vlm/bin/python -m pip install -r requirements-vlm.txt
.venv-vlm/bin/python - <<'PY'
import accelerate
import torch
import transformers

print(f"torch={torch.__version__}")
print(f"cuda={torch.cuda.is_available()}")
print(f"transformers={transformers.__version__}")
print(f"accelerate={accelerate.__version__}")
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available in the VLM environment")
PY
