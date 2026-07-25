#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
work_dir="data_video/work/vlm_shards"
mkdir -p "$work_dir"

exec 8>"$work_dir/relevance_pool.lock"
if ! flock -n 8; then
  echo "relevance-pool workflow is already running" >&2
  exit 2
fi

echo "waiting_for_post_vlm_rebuild=$(date -u +%FT%TZ)"
while pgrep -f '[r]un_post_vlm_rebuild.sh' >/dev/null; do
  sleep 30
done
if ! grep -q '^post_vlm_rebuild_complete=' "$work_dir/post_vlm_rebuild.log"; then
  echo "post-VLM rebuild did not complete successfully" >&2
  exit 1
fi

cleanup() {
  ./video_visual_embedding_service.sh stop || true
  ./video_embedding_service.sh stop || true
}
trap cleanup EXIT

export VIDEO_EMBEDDING_DEVICE=cuda:0
export VIDEO_EMBEDDING_PORT=8091
export VIDEO_VISUAL_CUDA_VISIBLE_DEVICES=1
export VIDEO_VISUAL_EMBEDDING_PORT=8092
./video_embedding_service.sh start
./video_visual_embedding_service.sh start

.venv/bin/python pool_video_relevance_candidates.py \
  --top-k-per-mode 20 \
  --modes bm25 dense visual hybrid tri_hybrid \
  --dense-endpoint http://127.0.0.1:8091 \
  --visual-endpoint http://127.0.0.1:8092 \
  --require-all-modes
.venv/bin/python validate_paper_relevance_pool.py

cleanup
trap - EXIT
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
echo "relevance_pool_complete=$(date -u +%FT%TZ)"
