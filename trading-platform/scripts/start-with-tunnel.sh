#!/usr/bin/env bash
# Start backend + public tunnel with auto-restart (interim until Render deploy)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  local bin="$ROOT/.bin/cloudflared"
  mkdir -p "$ROOT/.bin"
  if [[ ! -x "$bin" ]]; then
    echo "Installing cloudflared to $bin..."
    curl -fsSL -o "$bin" \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x "$bin"
  fi
  export PATH="$ROOT/.bin:$PATH"
}

ensure_backend() {
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    return 0
  fi
  pip3 install -q -r requirements.txt
  mkdir -p data
  echo "Starting backend on :8000..."
  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      echo "Backend healthy."
      return 0
    fi
    sleep 1
  done
  echo "Backend failed to start." >&2
  return 1
}

backend_watchdog() {
  while true; do
    if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      echo "[watchdog] Backend down — restarting..."
      pkill -f "uvicorn app.main:app" 2>/dev/null || true
      sleep 1
      ensure_backend || true
    fi
    sleep 15
  done
}

install_cloudflared
ensure_backend
backend_watchdog &
WATCHDOG_PID=$!
trap 'kill $WATCHDOG_PID 2>/dev/null || true' EXIT

echo "Starting Cloudflare tunnel (auto-restarts on failure)..."
echo "Set Vercel BACKEND_URL / BACKEND_WS_URL to the https://*.trycloudflare.com URL below."
while true; do
  cloudflared tunnel --url http://127.0.0.1:8000 || true
  echo "[tunnel] Restarting in 5s..."
  sleep 5
done
