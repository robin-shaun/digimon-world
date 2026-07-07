#!/usr/bin/env bash
# 启动 FastAPI 后端
# 开发模式: cd backend && ./run.sh
# 监听: 0.0.0.0:8000

set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"
exec python3 -m uvicorn digimon_world.api.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
