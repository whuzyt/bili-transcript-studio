#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8787

