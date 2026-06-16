#!/usr/bin/env bash
# Run the RAGAS evaluation against a running stack.
#
# Use this when `make` is unavailable (e.g. plain Windows Git Bash). It mirrors
# the Makefile `eval` target: verify the stack is up, then run run_ragas.py.
#
#   bash eval/run.sh            # evaluate against http://localhost:8000
#   RAG_API_BASE_URL=... bash eval/run.sh
#
# Set OPENAI_API_KEY (and the backend's ANTHROPIC_API_KEY) via the repo-root
# .env; run_ragas.py loads it automatically.
set -euo pipefail

BASE_URL="${RAG_API_BASE_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"

echo "Checking the stack at ${BASE_URL}/health ..."
if ! curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
  # /health answers 503 (with a body) when degraded; treat that as "up".
  if ! curl -s -o /dev/null -w '%{http_code}' "${BASE_URL}/health" | grep -q '503'; then
    echo "ERROR: stack not reachable at ${BASE_URL}." >&2
    echo "Start it: docker-compose -f infra/docker-compose.yml up --build" >&2
    exit 1
  fi
fi

echo "Indexing fixtures (idempotent) ..."
RAG_API_BASE_URL="${BASE_URL}" "${PYTHON}" "${SCRIPT_DIR}/index_fixtures.py"

echo "Running RAGAS evaluation ..."
RAG_API_BASE_URL="${BASE_URL}" "${PYTHON}" "${SCRIPT_DIR}/run_ragas.py" "$@"
