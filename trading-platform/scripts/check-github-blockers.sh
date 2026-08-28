#!/usr/bin/env bash
# Report GitHub check-suite blockers that prevent Render checksPass auto-deploy.
set -euo pipefail

REPO="${GITHUB_REPO:-apexweb-adam/apexweb-adam}"
API="https://api.github.com/repos/$REPO"

MAIN_SHA=$(curl -fsS "$API/git/ref/heads/main" | python3 -c "import json,sys; print(json.load(sys.stdin)['object']['sha'])")
echo "main: ${MAIN_SHA:0:12}"

COMBINED=$(curl -fsS "$API/commits/$MAIN_SHA/status" | python3 -c "import json,sys; print(json.load(sys.stdin).get('state','?'))")
echo "combined commit status: $COMBINED"
echo ""

python3 << PY
import json, sys, urllib.request

api = "$API"
sha = "$MAIN_SHA"
req = urllib.request.Request(
    f"{api}/commits/{sha}/check-suites?per_page=100",
    headers={"Accept": "application/vnd.github+json", "User-Agent": "ApexTradingPlatform/1.0"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    suites = json.load(resp).get("check_suites") or []

blocking = []
print("Check suites (non-GitHub Actions):")
for s in suites:
    app = (s.get("app") or {}).get("name") or "?"
    if app == "GitHub Actions":
        continue
    status = s.get("status")
    conclusion = s.get("conclusion")
    print(f"  {app}: status={status} conclusion={conclusion}")
    if status != "completed":
        blocking.append(f"{app} ({status})")
    elif conclusion not in ("success", "skipped", "neutral"):
        blocking.append(f"{app} ({conclusion})")

print("")
if blocking:
    print("BLOCKED — Render checksPass will not deploy until these clear:")
    for b in blocking:
        print(f"  - {b}")
    print("")
    print("Fix (pick one):")
    print("  1. Render Dashboard → apex-trading-backend → Manual Deploy → latest commit")
    print("     Then Settings → Auto-Deploy → On Commit (not After CI Checks Pass)")
    print("  2. GitHub → https://github.com/$REPO/settings/installations")
    print("     Configure each app → remove access to this repo (Vercel, Netlify, Supabase, Cursor, Claude)")
    print("  3. Add RENDER_API_KEY to GitHub secrets + Render env")
    print("")
    print("See trading-platform/DEPLOY_UNBLOCK.md")
    sys.exit(1)

print("No third-party check-suite blockers detected.")
PY

RENDER="${RENDER_URL:-https://apex-trading-backend.onrender.com}"
if curl -sf "$RENDER/api/status" >/dev/null 2>&1; then
  python3 << PY
import json, urllib.request
url = "$RENDER/api/status"
with urllib.request.urlopen(url, timeout=30) as resp:
    d = json.load(resp).get("deploy") or {}
deployed = (d.get("git_commit") or "")[:12]
main = (d.get("latest_main_commit") or "")[:12]
print(f"Render deployed: {deployed or '?'}  main: {main or '?'}  stale: {d.get('is_stale')}")
blocker = d.get("github_checks_blocker")
if blocker and blocker.get("blocked"):
    print("Production github_checks_blocker:", blocker.get("blocking_contexts"))
PY
fi
