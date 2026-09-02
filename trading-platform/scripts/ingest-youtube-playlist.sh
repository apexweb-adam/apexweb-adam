#!/usr/bin/env bash
# Ingest user YouTube playlist metadata into content-study knowledge base.
# Full transcript watch requires yt-dlp + Whisper (see claude-watch skill).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OEMBED_JSON="${1:-$ROOT/backend/fixtures/youtube-playlist-oembed.json}"

if [[ ! -f "$OEMBED_JSON" ]]; then
  echo "Missing oEmbed JSON: $OEMBED_JSON" >&2
  exit 1
fi

echo "Playlist metadata: $OEMBED_JSON"
python3 - <<'PY' "$OEMBED_JSON"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
items = json.loads(path.read_text())
from app.intelligence.youtube_playlist_knowledge import (
  PLAYLIST_VIDEO_COUNT,
  YOUTUBE_PLAYLIST_KNOWLEDGE,
  all_playlist_knowledge,
)

curated_ids = {r["video_id"] for r in YOUTUBE_PLAYLIST_KNOWLEDGE}
oembed_ids = {i["id"] for i in items}
missing = oembed_ids - curated_ids
extra = len(all_playlist_knowledge(items)) - len(YOUTUBE_PLAYLIST_KNOWLEDGE)

print(f"oEmbed videos: {len(items)}")
print(f"Curated playlist rows: {len(YOUTUBE_PLAYLIST_KNOWLEDGE)} (expected {PLAYLIST_VIDEO_COUNT})")
print(f"Curated coverage: {len(oembed_ids & curated_ids)}/{len(oembed_ids)}")
if missing:
  print(f"oEmbed-only (fallback ingest): {len(missing)}")
print(f"Total knowledge rows with oEmbed merge: {len(all_playlist_knowledge(items))} (+{extra} fallback)")
PY

echo ""
echo "Apply on production (requires TRADINGVIEW_WEBHOOK_SECRET):"
echo "  curl -X POST \"\$BACKEND/api/admin/run-content-study\" -H 'Content-Type: application/json' -d '{\"secret\":\"...\"}'"
