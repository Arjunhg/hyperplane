#!/bin/bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ubuntu/hyperplane}"
cd "$APP_DIR"

cleanup() {
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$APP_DIR/main_app" \
  --port=61336 \
  --mode=peer \
  --buyer-or-seller=buyer \
  --list-of-sellers-source=env \
  --envFile=.buyer-env \
| MLAT_READ_STDIN=1 uv run --project python \
    uvicorn api.server:app --host 0.0.0.0 --port 8000

wait