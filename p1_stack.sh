#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p logs
api_pid_file="logs/p1_api.pid"
worker_pid_file="logs/p1_worker.pid"
api_log="logs/p1_api.log"
worker_log="logs/p1_worker.log"
api_port="${P1_API_PORT:-8000}"

running() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

start_process() {
  local pid_file="$1" log_file="$2"; shift 2
  if running "$pid_file"; then return; fi
  rm -f "$pid_file"
  nohup "$@" >"$log_file" 2>&1 </dev/null &
  echo "$!" >"$pid_file"
}

stop_process() {
  local pid_file="$1" label="$2"
  if ! running "$pid_file"; then rm -f "$pid_file"; echo "$label=stopped"; return; fi
  local pid; pid="$(cat "$pid_file")"; kill "$pid"
  for _ in $(seq 1 20); do
    if ! kill -0 "$pid" 2>/dev/null; then rm -f "$pid_file"; echo "$label=stopped"; return; fi
    sleep 1
  done
  echo "$label failed to stop pid=$pid" >&2; return 1
}

start() {
  export VIDEO_RETRIEVAL_MODE=tri_hybrid VIDEO_REQUIRE_EXACT_MODE=1 USER_VIDEO_ASYNC_MODE=spool
  export VIDEO_DENSE_ENDPOINT="${VIDEO_DENSE_ENDPOINT:-http://127.0.0.1:8091}"
  export VIDEO_VISUAL_DENSE_ENDPOINT="${VIDEO_VISUAL_DENSE_ENDPOINT:-http://127.0.0.1:8092}"
  ./video_embedding_service.sh start
  ./video_visual_embedding_service.sh start
  start_process "$worker_pid_file" "$worker_log" .venv/bin/python video_job_worker.py
  start_process "$api_pid_file" "$api_log" .venv/bin/python -m uvicorn api_server:app --host 127.0.0.1 --port "$api_port" --workers 1
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${api_port}/health" | grep -q '"status":"ok"'; then
      echo "p1_stack=ready url=http://127.0.0.1:${api_port}/demo"; return
    fi
    sleep 1
  done
  echo "P1 stack failed readiness; inspect $api_log and $worker_log" >&2
  release
  return 1
}

status_all() {
  running "$api_pid_file" && echo "p1_api=running pid=$(cat "$api_pid_file")" || echo "p1_api=stopped"
  running "$worker_pid_file" && echo "p1_worker=running pid=$(cat "$worker_pid_file")" || echo "p1_worker=stopped"
  ./video_embedding_service.sh status || true
  ./video_visual_embedding_service.sh status || true
  curl -fsS "http://127.0.0.1:${api_port}/health" || true
}

release() {
  stop_process "$api_pid_file" p1_api
  stop_process "$worker_pid_file" p1_worker
  ./video_visual_embedding_service.sh stop
  ./video_embedding_service.sh stop
  echo "p1_gpu_resources=released"
}

case "${1:-}" in
  start) start ;;
  stop|release) release ;;
  restart) release; start ;;
  status) status_all ;;
  *) echo "usage: $0 {start|stop|restart|status|release}" >&2; exit 2 ;;
esac
