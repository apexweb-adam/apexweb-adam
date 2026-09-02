"""Tests for user YouTube playlist knowledge ingestion."""

from app.intelligence.content_study import (
  TRADING_KNOWLEDGE_BASE,
  YOUTUBE_IMPACT_PATTERNS,
  _extract_youtube_impact,
)
from app.intelligence.youtube_playlist_knowledge import (
  PLAYLIST_VIDEO_COUNT,
  YOUTUBE_PLAYLIST_KNOWLEDGE,
  all_playlist_knowledge,
  ingest_youtube_oembed,
)


def test_playlist_has_46_unique_videos():
  ids = [row["video_id"] for row in YOUTUBE_PLAYLIST_KNOWLEDGE]
  assert len(ids) == PLAYLIST_VIDEO_COUNT
  assert len(set(ids)) == PLAYLIST_VIDEO_COUNT


def test_trading_knowledge_base_includes_playlist():
  playlist_urls = {row["url"] for row in YOUTUBE_PLAYLIST_KNOWLEDGE}
  kb_urls = {row["url"] for row in TRADING_KNOWLEDGE_BASE if row.get("source_type") == "youtube"}
  assert playlist_urls.issubset(kb_urls)


def test_axiom_tutorial_impact_pattern():
  impact, confidence = _extract_youtube_impact(
    "The ONLY Axiom Trading Tutorial You Need in 2026",
    "axiom wallet smart money flow",
  )
  assert impact is not None
  assert "axiom" in impact.lower()
  assert confidence >= 0.85


def test_orderflow_robbins_impact_pattern():
  impact, confidence = _extract_youtube_impact(
    "Orderflow strategy Robbins Cup champion",
    "volume profile at liquidity",
  )
  assert impact is not None
  assert "orderflow" in impact.lower() or "volume" in impact.lower()
  assert confidence >= 0.8


def test_memecoin_scam_impact_pattern():
  impact, confidence = _extract_youtube_impact(
    "How to Identify Memecoin Scams",
    "rug pull scam markers on solana",
  )
  assert impact is not None
  assert "scam" in impact.lower() or "liquidity" in impact.lower()
  assert confidence >= 0.85


def test_tradingview_claude_impact_pattern():
  impact, confidence = _extract_youtube_impact(
    "Claude + TradingView automation webhook",
    "AI trading bot with tradingview alerts",
  )
  assert impact is not None
  assert confidence >= 0.75


def test_ingest_oembed_skips_known_ids():
  extras = ingest_youtube_oembed(
    [{"id": "eRkkrqhf_Kg", "title": "dup", "author": "x"}, {"id": "newvid12345", "title": "New", "author": "y"}]
  )
  assert len(extras) == 1
  assert extras[0]["url"] == "https://youtu.be/newvid12345"


def test_all_playlist_knowledge_merges_oembed():
  rows = all_playlist_knowledge([{"id": "zzzzunknown", "title": "Extra", "author": "z"}])
  assert len(rows) == PLAYLIST_VIDEO_COUNT + 1
