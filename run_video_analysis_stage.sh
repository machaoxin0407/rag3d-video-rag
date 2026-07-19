#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

stage="${1:-}"
case "$stage" in
  scenes)
    exec .venv/bin/python segment_video_sources.py \
      --threshold 0.32 \
      --minimum-scene-seconds 2
    ;;
  asr)
    # The server cannot currently reach huggingface.co directly. Operators can
    # override this endpoint when direct access is restored.
    export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
    export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
    asr_libs="$(
      .venv-asr/bin/python -c \
        'import nvidia.cublas.lib; import nvidia.cudnn.lib; print(nvidia.cublas.lib.__path__[0] + ":" + nvidia.cudnn.lib.__path__[0])'
    )"
    export LD_LIBRARY_PATH="${asr_libs}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
    exec .venv-asr/bin/python transcribe_video_sources.py \
      --model large-v3 \
      --device cuda \
      --device-index 0 \
      --compute-type float16 \
      --beam-size 5
    ;;
  ocr)
    exec .venv-ocr/bin/python ocr_video_keyframes.py \
      --language-profile de \
      --ocr-version PP-OCRv5 \
      --device cpu \
      --minimum-score 0.50
    ;;
  evidence)
    exec .venv/bin/python build_video_evidence.py
    ;;
  *)
    echo "usage: $0 {scenes|asr|ocr|evidence}" >&2
    exit 2
    ;;
esac
