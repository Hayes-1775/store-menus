#!/usr/bin/env bash

WORKFLOW_OPTIMIZER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW_OPTIMIZER_PYTHON="${PYTHON:-/Users/mikehayes/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3}"
WORKFLOW_OPTIMIZER_SCRIPT="$WORKFLOW_OPTIMIZER_ROOT/scripts/workflow-optimizer.py"
WORKFLOW_RUN_ID="${WORKFLOW_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-$$}"

workflow_now_ms() {
  "$WORKFLOW_OPTIMIZER_PYTHON" -c 'import time; print(int(time.time() * 1000))'
}

workflow_record_step() {
  local workflow="$1"
  local step="$2"
  local status="$3"
  local start_ms="$4"
  local end_ms="$5"
  local method="${6:-local-script}"
  local action_type="${7:-}"
  local wait_ms="${8:-0}"
  local mouse_distance_px="${9:-0}"
  local retries="${10:-0}"
  local error_message="${11:-}"
  local user_override="${12:-}"

  "$WORKFLOW_OPTIMIZER_PYTHON" "$WORKFLOW_OPTIMIZER_SCRIPT" record-step \
    --workflow "$workflow" \
    --run-id "$WORKFLOW_RUN_ID" \
    --step "$step" \
    --status "$status" \
    --started-at-ms "$start_ms" \
    --ended-at-ms "$end_ms" \
    --method "$method" \
    --action-type "$action_type" \
    --wait-ms "$wait_ms" \
    --mouse-distance-px "$mouse_distance_px" \
    --retries "$retries" \
    --error-message "$error_message" \
    --user-override "$user_override" >/dev/null 2>&1 || true
}

workflow_run_timed_step() {
  local workflow="$1"
  local step="$2"
  local method="$3"
  local action_type="${4:-other}"
  shift 4

  local start_ms end_ms status
  start_ms="$(workflow_now_ms)"
  if "$@"; then
    status="success"
  else
    local exit_code=$?
    status="failure"
    end_ms="$(workflow_now_ms)"
    workflow_record_step "$workflow" "$step" "$status" "$start_ms" "$end_ms" "$method" "$action_type" 0 0 0 "command failed"
    return "$exit_code"
  fi

  end_ms="$(workflow_now_ms)"
  workflow_record_step "$workflow" "$step" "$status" "$start_ms" "$end_ms" "$method" "$action_type"
}
