#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
work_dir="data_video/work/relevance_ai"
mkdir -p "$work_dir"

# A long first pass may already hold this lock. Wait without disturbing it,
# then use the updated parser to retry only unresolved journal entries.
while ! flock -n "$work_dir/run.lock" -c true; do
  sleep 30
done

for attempt in 1 2 3; do
  echo "relevance_finalize_attempt=$attempt"
  if ./run_video_relevance_preannotation.sh; then
    .venv/bin/python prepare_paper_relevance_r1_bundle.py --materialize-media
    echo "relevance_stage_finalized=$(date -u +%FT%TZ)"
    exit 0
  fi
done

echo "Relevance stage still has unresolved records after three retries" >&2
exit 1
