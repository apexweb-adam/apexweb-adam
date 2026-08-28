"""Tests for gate entry tightening helpers."""

from app.engines.gate_entry_guard import (
  GateEntryTightening,
  bot_min_sentiment,
  in_shadow_graduation_nudge,
  shadow_entry_min_signal,
  shadow_min_signal_boost,
  shadow_requires_macd,
)


def test_shadow_min_signal_boost_per_bot():
  assert shadow_min_signal_boost("commodities") > shadow_min_signal_boost("stocks_futures")
  assert shadow_min_signal_boost("crypto") >= 0.12
  assert shadow_min_signal_boost("unknown_bot") == 0.10


def test_shadow_graduation_nudge_eases_commodities():
  assert in_shadow_graduation_nudge("commodities", 0.50) is True
  assert in_shadow_graduation_nudge("commodities", 0.40) is False
  assert shadow_min_signal_boost("commodities", bot_win_rate=0.50) < shadow_min_signal_boost(
    "commodities"
  )
  assert shadow_requires_macd(
    "commodities",
    bot_win_rate=0.50,
    gate_tightening=GateEntryTightening(
      active=False,
      win_rate=1.0,
      min_sentiment=0.0,
      require_macd_bullish=False,
      min_composite_boost=0.0,
    ),
    shadow_mode=True,
  ) is False


def test_shadow_entry_min_signal_nudge_lowers_threshold():
  from app.engines.gate_entry_guard import shadow_entry_min_signal

  strict = shadow_entry_min_signal("commodities", 0.28)
  nudged = shadow_entry_min_signal("commodities", 0.28, bot_win_rate=0.50)
  assert nudged < strict


def test_bot_min_sentiment_inactive():
  tightening = GateEntryTightening(
    active=False,
    win_rate=0.5,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
  )
  assert bot_min_sentiment("stocks_futures", tightening) == 0.0


def test_bot_min_sentiment_active_uses_floor():
  tightening = GateEntryTightening(
    active=True,
    win_rate=0.48,
    min_sentiment=0.05,
    require_macd_bullish=True,
    min_composite_boost=0.02,
  )
  assert bot_min_sentiment("stocks_futures", tightening) == 0.05
  assert bot_min_sentiment("polymarket", tightening) == 0.12


def test_gate_entry_tightening_blocked_entries():
  tightening = GateEntryTightening(
    active=True,
    win_rate=0.47,
    min_sentiment=0.06,
    require_macd_bullish=True,
    min_composite_boost=0.03,
    blocked_new_entries=frozenset({"crypto", "commodities", "polymarket"}),
  )
  assert "crypto" in tightening.blocked_new_entries
  assert "stocks_futures" not in tightening.blocked_new_entries
