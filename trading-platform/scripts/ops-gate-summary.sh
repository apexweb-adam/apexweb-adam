#!/usr/bin/env bash
# Print profitability gate + integration health lines for operator scripts.
# Non-blocking; exits 0 even when warnings are printed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/fetch_json.sh
source "$ROOT/scripts/lib/fetch_json.sh"
BACKEND="${BACKEND_URL:-https://apex-trading-backend.onrender.com}"

if ! check_backend_suspension "$BACKEND" 2>/dev/null; then
  echo "Profitability gate: backend billing-suspended (see Render dashboard)"
  python3 - << 'PY' 2>/dev/null || true
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
if now.isoweekday() != 1 or now.hour < 13:
    raise SystemExit(0)
session_end = now.replace(hour=21, minute=0, second=0, microsecond=0)
catchup_left = max(0, int((session_end.timestamp() - now.timestamp()) // 60))
if catchup_left > 0 and now.hour < 21:
    print(f"  post_grace_catchup_min={catchup_left} until 21:00 UTC")
    print("  verify=bash trading-platform/scripts/verify-post-outage-recovery.sh --watch 90")
PY
  exit 0
fi

PROFIT=$(curl -fsS -m 20 "$BACKEND/api/profitability" 2>/dev/null || echo "{}")
PROFIT_JSON="$PROFIT" python3 << 'PY'
import json, os, sys
data = json.loads(os.environ.get("PROFIT_JSON") or "{}")
if not data:
    sys.exit(0)
paused = data.get("paused_bots") or []
day = data.get("verification_day")
remaining = data.get("verification_days_remaining")
wr = data.get("win_rate")
pf = data.get("profit_factor")
trades = data.get("total_trades")
pnl = data.get("total_pnl")
ready = data.get("live_trading_ready")
parts = []
if paused:
    parts.append(f"paused={paused}")
if day is not None:
    parts.append(f"verification day {day}/30 ({remaining}d left)")
if wr is not None and pf is not None:
    parts.append(f"WR={wr:.0%} PF={pf:.2f} trades={trades}")
if pnl is not None:
    parts.append(f"PnL=${pnl:+.2f}")
parts.append(f"live_ready={ready}")
print("Profitability gate: " + "; ".join(parts))
PY

PER_BOT=$(curl -fsS -m 25 "$BACKEND/api/gate/per-bot" 2>/dev/null || echo "{}")
PER_BOT_JSON="$PER_BOT" python3 << 'PY'
import json, os, sys
data = json.loads(os.environ.get("PER_BOT_JSON") or "{}")
bots = data.get("bots") or {}
if not bots:
    sys.exit(0)
paused_rows = []
for bot_type, stats in sorted(bots.items()):
    if not stats.get("paused"):
        continue
    progress = (stats.get("graduation_progress") or {}).get("overall_pct")
    progress_label = f"{progress:.0%}" if progress is not None else "?"
    ready = stats.get("graduation_ready")
    blockers = stats.get("graduation_blockers") or []
    trades = stats.get("total_trades")
    wr = stats.get("win_rate")
    pf = stats.get("profit_factor")
    line = f"  {bot_type}: graduation={progress_label} ready={ready} trades={trades}"
    if wr is not None and pf is not None:
        line += f" WR={wr:.0%} PF={pf}"
    if blockers:
        line += f" needs={blockers}"
    paused_rows.append(line)
if paused_rows:
    print("Per-bot graduation (paused):")
    for row in paused_rows:
        print(row)
PY

STATUS=$(curl -fsS -m 45 "$BACKEND/api/status" 2>/dev/null || echo "{}")
STATUS_JSON="$STATUS" python3 << 'PY'
import json, os, sys
data = json.loads(os.environ.get("STATUS_JSON") or "{}")
if not data:
    sys.exit(0)
integrations = data.get("integrations") or {}
deploy = data.get("deploy") or {}
intel = data.get("intelligence") or {}
learning = data.get("learning") or {}
lines = []
if learning:
    lines.append(
        "Learning loop: "
        f"analyses={learning.get('trade_analyses')} "
        f"reviews={learning.get('daily_reviews')} "
        f"pending_insights={learning.get('insights_pending')}"
    )
    intel_count = learning.get("intel_pattern_count") or 0
    if intel_count:
        lines.append(
            f"WARN: intel pattern alerts={intel_count} — recurring intel-driven losses flagged in daily reviews"
        )
        for alert in (learning.get("intel_pattern_alerts") or [])[:3]:
            lines.append(f"  {alert}")
content = data.get("content_study") or {}
applied = content.get("insights_applied") or 0
recent = content.get("recent") or []
if applied or recent:
    lines.append(
        f"Content study: applied={applied} recent_highlights={len(recent)}"
    )
    for row in recent[:3]:
        label = row.get("source_label") or row.get("source_type") or "unknown"
        title = (row.get("title") or "")[:48]
        state = "applied" if row.get("applied") else "pending"
        lines.append(f"  [{label}] {title} ({state})")
degraded = [s.get("source") for s in (intel.get("sources") or []) if s.get("status") == "degraded"]
if degraded:
    lines.append(f"WARN: intel degraded: {', '.join(degraded)}")
if deploy.get("vercel_bundle_behind_expected"):
    exp = deploy.get("expected_dashboard_bundle") or "?"
    act = deploy.get("vercel_bundle_revision") or "?"
    lines.append(f"WARN: dashboard bundle behind expected ({act} vs {exp})")
mins = integrations.get("fomo_bearer_minutes_remaining")
polling = integrations.get("fomo_bearer_polling_active")
configured = integrations.get("fomo_bearer_configured")
if configured and not polling:
    if mins is not None and int(mins) < 0:
        lines.append(f"WARN: fomo bearer expired ({mins}min) — refresh via userscript or fomo-set-bearer.sh")
    else:
        lines.append("WARN: fomo bearer polling inactive — intel may be degraded")
hint = integrations.get("fomo_bearer_refresh_hint")
if hint and lines:
    lines.append(f"  {hint}")
for line in lines:
    print(line)
PY
