#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

.venv/bin/python -m app.cli \
  "https://www.bilibili.com/video/BV18V411m76n" \
  --model large-v3-turbo \
  --language zh \
  --device auto \
  --compute-type auto

