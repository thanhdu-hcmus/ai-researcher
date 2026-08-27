#!/usr/bin/env bash
set -euo pipefail

if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

uvicorn ai_researcher.main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
