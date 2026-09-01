"""Tests for political event classification."""

from app.intelligence.political_signals import (
  classify_political_event,
  format_political_content,
  political_category,
)


def test_classify_tariff_targets_commodities():
  event_type, symbols, bots = classify_political_event(
    "US announces new tariff on steel imports"
  )
  assert event_type == "tariff"
  assert "GC" in symbols
  assert "commodities" in bots


def test_classify_fed_targets_stocks_and_commodities():
  event_type, symbols, bots = classify_political_event("Fed signals rate cut at FOMC meeting")
  assert event_type == "monetary"
  assert "stocks_futures" in bots
  assert "commodities" in bots


def test_classify_election_targets_polymarket():
  event_type, _, bots = classify_political_event("Election poll shows tight presidential race")
  assert event_type == "election"
  assert "polymarket" in bots


def test_classify_geopolitics_safe_haven():
  event_type, symbols, bots = classify_political_event("Escalation in Gaza raises oil supply fears")
  assert event_type == "geopolitics"
  assert "GC" in symbols or "CL" in symbols
  assert "commodities" in bots


def test_classify_general_fallback():
  event_type, symbols, bots = classify_political_event("Congress passes routine budget bill")
  assert event_type == "general"
  assert "POLITICAL" in symbols
  assert len(bots) >= 2


def test_political_category_prefix():
  assert political_category("tariff") == "political:tariff"


def test_format_political_content_includes_targets():
  text = format_political_content("Headline body", "tariff", ["commodities", "stocks_futures"])
  assert "[tariff]" in text
  assert "commodities" in text
