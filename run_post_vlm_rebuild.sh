#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
work_dir="data_video/work/vlm_shards"
mkdir -p "$work_dir"

exec 9>"$work_dir/post_vlm_rebuild.lock"
if ! flock -n 9; then
  echo "post-VLM rebuild is already running" >&2
  exit 2
fi

echo "waiting_for_vlm_workers=$(date -u +%FT%TZ)"
while pgrep -f '[c]aption_video_scenes.py' >/dev/null; do
  sleep 30
done

echo "merging_vlm_shards=$(date -u +%FT%TZ)"
.venv/bin/python merge_vlm_shards.py \
  --runs "$work_dir/runs_shard_0.csv" \
  --runs "$work_dir/runs_shard_1.csv" \
  --captions "$work_dir/captions_shard_0.csv" \
  --captions "$work_dir/captions_shard_1.csv"

echo "building_evidence=$(date -u +%FT%TZ)"
./run_video_analysis_stage.sh evidence
.venv/bin/python validate_video_analysis.py

echo "building_indexes=$(date -u +%FT%TZ)"
.venv-embedding/bin/python build_video_dense_index.py \
  --device cuda:0 \
  >"$work_dir/dense_index.log" 2>&1 &
dense_pid=$!
CUDA_VISIBLE_DEVICES=1 .venv-visual-embedding/bin/python build_video_visual_index.py \
  >"$work_dir/visual_index.log" 2>&1 &
visual_pid=$!

set +e
wait "$dense_pid"
dense_status=$?
wait "$visual_pid"
visual_status=$?
set -e
if [[ "$dense_status" -ne 0 || "$visual_status" -ne 0 ]]; then
  echo "index failure: dense=$dense_status visual=$visual_status" >&2
  exit 1
fi

.venv/bin/python validate_video_retrieval.py
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
echo "post_vlm_rebuild_complete=$(date -u +%FT%TZ)"
