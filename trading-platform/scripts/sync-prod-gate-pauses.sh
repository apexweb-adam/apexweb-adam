#!/usr/bin/env bash
# Pause chronic underperformers on production when /api/admin/sync-gate-pauses is unavailable (stale Render).
# Prefers sync-gate-pauses on r79+; falls back to per-bot set-bot-paused using portfolio stats.
set -euo pipefail

BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"
SECRET="${TRADINGVIEW_WEBHOOK_SECRET:-}"

if [[ -z "$SECRET" && -f "$(dirname "$0")/../.env" ]]; then
  SECRET=$(grep '^TRADINGVIEW_WEBHOOK_SECRET=' "$(dirname "$0")/../.env" | cut -d= -f2- || true)
fi

if [[ -z "$SECRET" ]]; then
  echo "Set TRADINGVIEW_WEBHOOK_SECRET or add to trading-platform/.env" >&2
  exit 1
fi

echo "Backend: $BACKEND"

SYNC_HTTP=$(curl -sS -o /tmp/sync-gate.json -w "%{http_code}" -X POST \
  "$BACKEND/api/admin/sync-gate-pauses" \
  -H 'Content-Type: application/json' \
  -d "{\"secret\":\"$SECRET\"}" || echo "000")

if [[ "$SYNC_HTTP" == "200" ]]; then
  cat /tmp/sync-gate.json
  echo ""
  exit 0
fi

echo "sync-gate-pauses unavailable (HTTP $SYNC_HTTP) — falling back to set-bot-paused"
echo ""

export BACKEND SECRET
curl -fsS "$BACKEND/api/portfolios" -o /tmp/portfolios.json
python3 << 'PY'
import json, subprocess, os, sys

backend = os.environ["BACKEND"]
secret = os.environ["SECRET"]
min_trades = 15
max_wr = 0.40
skip = {"stocks_futures"}

with open("/tmp/portfolios.json") as f:
    data = json.load(f)
portfolios = data if isinstance(data, list) else data.get("portfolios", [])

paused = []
for p in portfolios:
    bot = p.get("bot_type")
    trades = int(p.get("total_trades") or 0)
    wr = float(p.get("win_rate") or 0)
    if bot in skip or trades < min_trades or wr >= max_wr:
        continue
    payload = json.dumps({"secret": secret, "bot_type": bot, "paused": True})
    result = subprocess.run(
        ["curl", "-fsS", "-X", "POST", f"{backend}/api/admin/set-bot-paused",
         "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Failed to pause {bot}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout.strip())
    paused.append(bot)

if not paused:
    print("No underperformers to pause (or already paused).")
else:
    print(f"Paused: {', '.join(paused)}")
PY

curl -fsS "$BACKEND/api/status" | python3 -c "
import json, sys
g = json.load(sys.stdin).get('profitability_gate', {})
print(f\"Gate WR: {g.get('win_rate')} trades: {g.get('total_trades')} paused: {g.get('paused_bots')}\")
"
