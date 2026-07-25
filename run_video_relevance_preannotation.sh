#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
work_dir="data_video/work/relevance_ai"
mkdir -p "$work_dir"
declare -a pids=()

exec 7>"$work_dir/run.lock"
if ! flock -n 7; then
  echo "AI relevance pre-annotation is already running" >&2
  exit 2
fi

for shard in 0 1; do
  CUDA_VISIBLE_DEVICES="$shard" .venv-vlm/bin/python preannotate_video_relevance.py \
    --journal "$work_dir/annotations_shard_${shard}.jsonl" \
    --shard-index "$shard" \
    --shard-count 2 \
    --device cuda:0 \
    >"$work_dir/worker_${shard}.log" 2>&1 &
  pids[$shard]=$!
done

set +e
wait "${pids[0]}"
status_0=$?
wait "${pids[1]}"
status_1=$?
set -e
if [[ "$status_0" -ne 0 || "$status_1" -ne 0 ]]; then
  echo "AI relevance shard failure: shard0=$status_0 shard1=$status_1" >&2
  exit 1
fi

.venv/bin/python merge_video_relevance_preannotations.py \
  --journal "$work_dir/annotations_shard_0.jsonl" \
  --journal "$work_dir/annotations_shard_1.jsonl"
.venv/bin/python validate_video_relevance_preannotations.py
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader
echo "video_relevance_preannotation_complete=$(date -u +%FT%TZ)"
