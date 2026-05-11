#!/usr/bin/env bash
# Fixed canonical multibot regression suite for Hermes multi-bot runtime.
#
# This suite is the single source of truth for "multibot" verification.
# Note: tests/test_topic_binding.py lives outside tests/gateway/ because
# topic_binding is a top-level multi-bot isolation primitive (per-bot
# topic registry). It is intentionally included here.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Locate pytest. Honor HERMES_PYTEST override, else probe common venv paths.
PYTEST="${HERMES_PYTEST:-}"
if [[ -z "$PYTEST" ]]; then
  for candidate in \
    "/usr/local/lib/hermes-agent/venv/bin/pytest" \
    "$REPO_ROOT/.venv/bin/pytest" \
    "$REPO_ROOT/venv/bin/pytest"; do
    if [[ -x "$candidate" ]]; then
      PYTEST="$candidate"
      break
    fi
  done
fi
if [[ -z "$PYTEST" ]]; then
  PYTEST="pytest"
fi

exec "$PYTEST" \
  tests/gateway/test_multibot_*.py \
  tests/gateway/test_session_context_multibot.py \
  tests/gateway/test_router.py \
  tests/gateway/test_registry.py \
  tests/gateway/test_restart_notification.py \
  tests/gateway/test_restart_resume_pending.py \
  tests/gateway/test_model_switch_persistence.py \
  tests/gateway/test_api_server_toolset.py \
  tests/gateway/test_feishu_comment.py \
  tests/test_topic_binding.py \
  "$@"
