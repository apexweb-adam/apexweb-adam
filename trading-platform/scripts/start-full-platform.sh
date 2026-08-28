#!/usr/bin/env bash
# Start backend + dashboard + public Cloudflare tunnels (24/7 paper trading CRM).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-3000}"

install_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    return 0
  fi
  local bin="$ROOT/.bin/cloudflared"
  mkdir -p "$ROOT/.bin"
  if [[ ! -x "$bin" ]]; then
    echo "Installing cloudflared..."
    curl -fsSL -o "$bin" \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
    chmod +x "$bin"
  fi
  export PATH="$ROOT/.bin:$PATH"
}

start_tunnel() {
  local port="$1"
  local out_file="$2"
  local label="$3"
  local log_file="/tmp/${label}-tunnel.log"
  (
    while true; do
      : > "$log_file"
      cloudflared tunnel --url "http://127.0.0.1:${port}" 2>&1 | tee "$log_file" &
      local cf_pid=$!
      for _ in $(seq 1 90); do
        if [[ -s "$log_file" ]]; then
          local url
          url=$(rg -o 'https://[a-z0-9-]+\.trycloudflare\.com' "$log_file" | head -1 || true)
          if [[ -n "$url" ]]; then
            echo "$url" > "$out_file"
            echo "[$label] public $url"
            break
          fi
        fi
        sleep 1
      done
      wait "$cf_pid" 2>/dev/null || true
      echo "[$label] tunnel restarting in 5s..."
      sleep 5
    done
  ) &
}

ensure_backend() {
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    return 0
  fi
  pip3 install -q -r "$ROOT/backend/requirements.txt"
  mkdir -p "$ROOT/backend/data"
  echo "Starting backend on :${BACKEND_PORT}..."
  (
    cd "$ROOT/backend"
    PYTHONPATH=. python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT"
  ) &
  for _ in $(seq 1 45); do
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
      echo "Backend healthy."
      return 0
    fi
    sleep 1
  done
  echo "Backend failed to start." >&2
  return 1
}

ensure_dashboard() {
  local backend_url="$1"
  if curl -sf "http://127.0.0.1:${DASHBOARD_PORT}/api/config" >/dev/null 2>&1; then
    return 0
  fi
  if [[ ! -d "$ROOT/dashboard/node_modules" ]]; then
    (cd "$ROOT/dashboard" && npm ci)
  fi
  echo "Starting dashboard on :${DASHBOARD_PORT} (backend=$backend_url)..."
  (
    cd "$ROOT/dashboard"
    BACKEND_URL="$backend_url" npx next dev -p "$DASHBOARD_PORT" -H 0.0.0.0
  ) &
  for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${DASHBOARD_PORT}/api/config" >/dev/null 2>&1; then
      echo "Dashboard healthy."
      return 0
    fi
    sleep 1
  done
  echo "Dashboard failed to start." >&2
  return 1
}

install_cloudflared
ensure_backend

BACKEND_TUNNEL_FILE="$ROOT/.tunnel-url"
DASHBOARD_TUNNEL_FILE="$ROOT/.dashboard-tunnel-url"
rm -f "$BACKEND_TUNNEL_FILE" "$DASHBOARD_TUNNEL_FILE"

start_tunnel "$BACKEND_PORT" "$BACKEND_TUNNEL_FILE" "api"
echo "Waiting for backend tunnel URL..."
for _ in $(seq 1 60); do
  [[ -s "$BACKEND_TUNNEL_FILE" ]] && break
  sleep 1
done
BACKEND_PUBLIC="$(cat "$BACKEND_TUNNEL_FILE" 2>/dev/null || true)"
if [[ -z "$BACKEND_PUBLIC" ]]; then
  echo "Backend tunnel URL not ready — using http://127.0.0.1:${BACKEND_PORT}" >&2
  BACKEND_PUBLIC="http://127.0.0.1:${BACKEND_PORT}"
fi
echo "Backend public: $BACKEND_PUBLIC"

ensure_dashboard "$BACKEND_PUBLIC"

start_tunnel "$DASHBOARD_PORT" "$DASHBOARD_TUNNEL_FILE" "crm"
echo "Waiting for dashboard tunnel URL..."
for _ in $(seq 1 60); do
  [[ -s "$DASHBOARD_TUNNEL_FILE" ]] && break
  sleep 1
done
DASHBOARD_PUBLIC="$(cat "$DASHBOARD_TUNNEL_FILE" 2>/dev/null || true)"

cat > "$ROOT/.platform-urls.json" << EOF
{
  "backend_url": "${BACKEND_PUBLIC}",
  "backend_ws": "wss://${BACKEND_PUBLIC#https://}/api/ws",
  "dashboard_url": "${DASHBOARD_PUBLIC:-}",
  "local_backend": "http://127.0.0.1:${BACKEND_PORT}",
  "local_dashboard": "http://127.0.0.1:${DASHBOARD_PORT}"
}
EOF

echo ""
echo "=== Apex Trading Platform (public) ==="
echo "CRM dashboard: ${DASHBOARD_PUBLIC:-pending}"
echo "Backend API:   $BACKEND_PUBLIC"
echo "WebSocket:     wss://${BACKEND_PUBLIC#https://}/api/ws"
echo "URLs saved:    $ROOT/.platform-urls.json"
echo ""

while true; do
  if ! curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" >/dev/null 2>&1; then
    echo "[watchdog] Backend down — exiting for supervisor restart"
    exit 1
  fi
  sleep 30
done
