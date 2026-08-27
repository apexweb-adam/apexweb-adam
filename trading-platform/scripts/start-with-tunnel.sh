#!/usr/bin/env bash
# Start backend + public tunnel for dashboard (interim until Render/Railway deploy)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"

pip3 install -q -r requirements.txt
mkdir -p data

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Installing cloudflared..."
  curl -fsSL -o /usr/local/bin/cloudflared \
    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x /usr/local/bin/cloudflared
fi

# Start backend in background if not already listening
if ! curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
  sleep 2
fi

echo "Starting Cloudflare tunnel on port 8000..."
echo "Set Vercel BACKEND_URL / BACKEND_WS_URL to the https://*.trycloudflare.com URL below."
exec cloudflared tunnel --url http://127.0.0.1:8000
