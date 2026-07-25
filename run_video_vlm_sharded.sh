#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"

work_dir="data_video/work/vlm_shards"
.venv/bin/python prepare_vlm_shards.py --shards 2 --output-dir "$work_dir"

run_worker() {
  local shard="$1"
  local device="$2"
  .venv-vlm/bin/python caption_video_scenes.py \
    --scenes "$work_dir/scenes_shard_${shard}.csv" \
    --runs "$work_dir/runs_shard_${shard}.csv" \
    --captions "$work_dir/captions_shard_${shard}.csv" \
    --frame-root data_video/vlm_frames \
    --model Qwen/Qwen3-VL-8B-Instruct \
    --device "$device" \
    --dtype bfloat16 \
    --offline \
    >"$work_dir/worker_${shard}.log" 2>&1
}

run_worker 0 cuda:0 &
pid0=$!
run_worker 1 cuda:1 &
pid1=$!

set +e
wait "$pid0"
status0=$?
wait "$pid1"
status1=$?
set -e
if [[ "$status0" -ne 0 || "$status1" -ne 0 ]]; then
  echo "VLM worker failure: shard0=$status0 shard1=$status1" >&2
  exit 1
fi

.venv/bin/python merge_vlm_shards.py \
  --runs "$work_dir/runs_shard_0.csv" \
  --runs "$work_dir/runs_shard_1.csv" \
  --captions "$work_dir/captions_shard_0.csv" \
  --captions "$work_dir/captions_shard_1.csv"
