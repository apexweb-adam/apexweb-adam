#!/usr/bin/env bash
# Start Apex Trading Platform backend (paper trading, 24/7 bots)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
pip3 install -q -r requirements.txt
mkdir -p data
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
