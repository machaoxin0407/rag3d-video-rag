#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
python3 -m virtualenv --clear .venv-embedding
.venv-embedding/bin/python -m pip install --upgrade pip
.venv-embedding/bin/python -m pip install -r requirements-video-embedding.txt
.venv-embedding/bin/python - <<'PY'
import sentence_transformers
import torch
import transformers

print(f"torch={torch.__version__}")
print(f"cuda={torch.cuda.is_available()}")
print(f"transformers={transformers.__version__}")
print(f"sentence_transformers={sentence_transformers.__version__}")
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available in the embedding environment")
PY
