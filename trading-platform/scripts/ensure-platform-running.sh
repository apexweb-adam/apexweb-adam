#!/usr/bin/env bash
# Start backend + Cloudflare tunnel + sync Vercel env (interim until Render is live)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMUX="${TMUX_BIN:-tmux -f /exec-daemon/tmux.portal.conf}"

session_exists() {
  $TMUX has-session -t "$1" 2>/dev/null
}

start_backend() {
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "✓ Backend already healthy on :8000"
    return 0
  fi
  if session_exists trading-backend; then
    echo "→ Restarting backend tmux session..."
    $TMUX send-keys -t trading-backend:0.0 C-c 2>/dev/null || true
    sleep 2
  else
    $TMUX new-session -d -s trading-backend -c "$ROOT/backend" -- "${SHELL:-bash}" -l
  fi
  $TMUX send-keys -t trading-backend:0.0 \
    "cd '$ROOT/backend' && pip3 install -q -r requirements.txt && mkdir -p data && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000" C-m
  for _ in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
      echo "✓ Backend started"
      return 0
    fi
    sleep 1
  done
  echo "✗ Backend failed to start — check: tmux attach -t trading-backend" >&2
  return 1
}

start_tunnel() {
  if session_exists cloudflared-tunnel; then
    echo "✓ Cloudflare tunnel session already running"
    return 0
  fi
  if ! command -v cloudflared >/dev/null 2>&1; then
    "$ROOT/scripts/start-with-tunnel.sh" &
    sleep 8
    return 0
  fi
  $TMUX new-session -d -s cloudflared-tunnel -c "$ROOT" -- "${SHELL:-bash}" -l
  $TMUX send-keys -t cloudflared-tunnel:0.0 \
    "cloudflared tunnel --url http://127.0.0.1:8000 2>&1 | tee /tmp/cloudflared.log" C-m
  sleep 6
  echo "✓ Cloudflare tunnel starting (see /tmp/cloudflared.log)"
}

sync_vercel() {
  if [[ -x "$ROOT/scripts/sync-tunnel-to-vercel.sh" ]]; then
    "$ROOT/scripts/sync-tunnel-to-vercel.sh" || true
  fi
}

echo "=== Apex Platform — ensure running ==="
start_backend
start_tunnel
sync_vercel
echo ""
echo "Dashboard: https://apex-trading-dashboard-flame.vercel.app"
echo "Local API: http://127.0.0.1:8000/api/status"
TUNNEL=$(rg -o 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log 2>/dev/null | tail -1 || true)
[[ -n "$TUNNEL" ]] && echo "Tunnel:    $TUNNEL"
echo ""
echo "Permanent backend: https://render.com/deploy?repo=https://github.com/apexweb-adam/apexweb-adam"
