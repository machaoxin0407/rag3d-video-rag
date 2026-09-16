#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

uv_version="0.11.29"
python_version="3.11"
model_revision="9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda"
model_root="models/Qwen3-VL-Embedding-2B"

python3 -m pip install --user "uv==${uv_version}"
export PATH="$HOME/.local/bin:$PATH"
uv python install "$python_version"
uv venv --clear --python "$python_version" .venv-visual-embedding
uv pip install --python .venv-visual-embedding/bin/python \
  --index-strategy unsafe-best-match \
  -r requirements-video-visual-embedding.txt

export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
.venv-visual-embedding/bin/hf download \
  Qwen/Qwen3-VL-Embedding-2B \
  --revision "$model_revision" \
  --local-dir "$model_root"

implementation_blob="36d45865735be96a1278a21c132ff640e2ae68ca"
actual_blob="$(git hash-object "${model_root}/scripts/qwen3_vl_embedding.py")"
if [[ "$actual_blob" != "$implementation_blob" ]]; then
  echo "Model-bundled implementation hash mismatch: ${actual_blob}" >&2
  exit 1
fi

.venv-visual-embedding/bin/python - <<'PY'
import sys
from pathlib import Path

import torch
import transformers

implementation_root = Path("models/Qwen3-VL-Embedding-2B/scripts").resolve()
sys.path.insert(0, str(implementation_root))
from qwen3_vl_embedding import Qwen3VLEmbedder  # noqa: E402

print(f"python={sys.version.split()[0]}")
print(f"torch={torch.__version__}")
print(f"cuda={torch.cuda.is_available()}")
print(f"transformers={transformers.__version__}")
print(f"implementation={implementation_root}")
print(f"embedder={Qwen3VLEmbedder.__name__}")
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available in the visual embedding environment")
PY
