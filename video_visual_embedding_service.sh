#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

pid_file="logs/video_visual_embedding_service.pid"
log_file="logs/video_visual_embedding_service.log"
host="${VIDEO_VISUAL_EMBEDDING_HOST:-127.0.0.1}"
port="${VIDEO_VISUAL_EMBEDDING_PORT:-8092}"

is_running() {
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null
}

start() {
  if is_running; then
    echo "video_visual_embedding_service=running pid=$(cat "$pid_file")"
    return
  fi
  mkdir -p logs
  rm -f "$pid_file"
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
  export HF_HUB_DISABLE_XET="${HF_HUB_DISABLE_XET:-1}"
  export CUDA_VISIBLE_DEVICES="${VIDEO_VISUAL_CUDA_VISIBLE_DEVICES:-1}"
  export VIDEO_VISUAL_EMBEDDING_HOST="$host"
  export VIDEO_VISUAL_EMBEDDING_PORT="$port"
  nohup .venv-visual-embedding/bin/python serve_video_visual_embeddings.py \
    >"$log_file" 2>&1 </dev/null &
  echo "$!" >"$pid_file"
  for _ in $(seq 1 60); do
    if curl -fs "http://${host}:${port}/health" >/dev/null; then
      echo "video_visual_embedding_service=ready pid=$(cat "$pid_file") endpoint=http://${host}:${port}"
      return
    fi
    sleep 1
  done
  stop
  echo "Visual embedding service failed readiness; inspect $log_file" >&2
  return 1
}

stop() {
  if ! is_running; then
    rm -f "$pid_file"
    echo "video_visual_embedding_service=stopped"
    return
  fi
  pid="$(cat "$pid_file")"
  kill "$pid"
  for _ in $(seq 1 20); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "video_visual_embedding_service=stopped"
      return
    fi
    sleep 1
  done
  echo "Visual embedding service did not stop within 20 seconds (pid=$pid)" >&2
  return 1
}

status() {
  if is_running; then
    echo "video_visual_embedding_service=running pid=$(cat "$pid_file") endpoint=http://${host}:${port}"
  else
    echo "video_visual_embedding_service=stopped"
    return 1
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *)
    echo "usage: $0 {start|stop|restart|status}" >&2
    exit 2
    ;;
esac
