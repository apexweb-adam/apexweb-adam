"""Tests for gate entry tightening helpers."""

from app.engines.gate_entry_guard import (
  GateEntryTightening,
  bot_min_sentiment,
  early_verification_active,
  gate_position_scale,
  in_shadow_graduation_nudge,
  shadow_entry_min_signal,
  shadow_intel_composite_override,
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
  assert in_shadow_graduation_nudge("crypto", 0.46) is True
  assert in_shadow_graduation_nudge("crypto", 0.44) is False
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


def test_early_verification_active():
  assert early_verification_active(11, 0.70) is True
  assert early_verification_active(30, 0.70) is False
  assert early_verification_active(11, 0.50) is False


def test_gate_position_scale_weak_signals():
  assert gate_position_scale(0.22, 0.20, early_boost=True) == 0.5
  assert gate_position_scale(0.26, 0.20, early_boost=True) == 0.75
  assert gate_position_scale(0.30, 0.20, early_boost=True) == 1.0
  assert gate_position_scale(0.22, 0.20, early_boost=False) == 1.0


def test_shadow_intel_composite_override_commodities_high_composite_only():
  assert shadow_intel_composite_override(
    "commodities",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.44,
    entry_min_signal=0.31,
    integration_boost=0.0,
  ) is True
  assert shadow_intel_composite_override(
    "commodities",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.40,
    entry_min_signal=0.31,
    integration_boost=0.0,
  ) is False


def test_shadow_intel_composite_override_commodities_nudge():
  assert shadow_intel_composite_override(
    "commodities",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.62,
    entry_min_signal=0.31,
    integration_boost=0.16,
  ) is True
  assert shadow_intel_composite_override(
    "commodities",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.40,
    entry_min_signal=0.31,
    integration_boost=0.16,
  ) is False
  assert shadow_intel_composite_override(
    "stocks_futures",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.62,
    entry_min_signal=0.31,
    integration_boost=0.16,
  ) is False


def test_shadow_intel_composite_override_crypto_high_composite_only():
  assert shadow_intel_composite_override(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.44,
    entry_min_signal=0.26,
    integration_boost=0.0,
  ) is True
  assert shadow_intel_composite_override(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.35,
    entry_min_signal=0.26,
    integration_boost=0.0,
  ) is False
  assert shadow_intel_composite_override(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.33,
    entry_min_signal=0.26,
    integration_boost=0.14,
  ) is True
  assert shadow_intel_composite_override(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.30,
    entry_min_signal=0.26,
    integration_boost=0.14,
  ) is False


def test_chronic_loser_blocks_shadow_entry_intel_bypass():
  from app.engines.gate_entry_guard import chronic_loser_blocks_shadow_entry

  assert chronic_loser_blocks_shadow_entry(
    "BTCUSDT",
    frozenset({"BTCUSDT"}),
    graduation_nudge=True,
    shadow_mode=True,
    intel_override=True,
  ) is False
  assert chronic_loser_blocks_shadow_entry(
    "BTCUSDT",
    frozenset({"BTCUSDT"}),
    graduation_nudge=True,
    shadow_mode=True,
    intel_override=False,
  ) is True
  assert chronic_loser_blocks_shadow_entry(
    "NVDA",
    frozenset({"NVDA"}),
    graduation_nudge=False,
    shadow_mode=False,
    intel_override=True,
  ) is True


def test_shadow_requires_macd_crypto_nudge_off():
  assert shadow_requires_macd(
    "crypto",
    bot_win_rate=0.46,
    gate_tightening=GateEntryTightening(
      active=False,
      win_rate=1.0,
      min_sentiment=0.0,
      require_macd_bullish=False,
      min_composite_boost=0.0,
    ),
    shadow_mode=True,
  ) is False


def test_early_verification_index_etf_entry_min_signal():
  from app.engines.gate_entry_guard import early_verification_index_etf_entry_min_signal

  assert early_verification_index_etf_entry_min_signal("SPY", 0.21, early_boost=True) == 0.29
  assert early_verification_index_etf_entry_min_signal("NVDA", 0.21, early_boost=True) == 0.21
  assert early_verification_index_etf_entry_min_signal("SPY", 0.21, early_boost=False) == 0.21


def test_apply_entry_min_signal_ease_early_verification_floor():
  from app.engines.gate_entry_guard import (
    EARLY_VERIFICATION_ENTRY_MIN_SIGNAL_FLOOR,
    apply_entry_min_signal_ease,
  )

  assert apply_entry_min_signal_ease(0.20, 0.03, early_boost=True) == 0.18
  assert apply_entry_min_signal_ease(0.20, 0.03, early_boost=False) == 0.17
  assert apply_entry_min_signal_ease(0.22, 0.10, early_boost=True) == EARLY_VERIFICATION_ENTRY_MIN_SIGNAL_FLOOR


def test_early_verification_raw_signal_ok():
  from app.engines.gate_entry_guard import early_verification_raw_signal_ok

  assert early_verification_raw_signal_ok(0.03, early_boost=True, bot_type="stocks_futures") is False
  assert early_verification_raw_signal_ok(0.12, early_boost=True, bot_type="stocks_futures") is True
  assert early_verification_raw_signal_ok(0.03, early_boost=False, bot_type="stocks_futures") is True
  assert early_verification_raw_signal_ok(0.03, early_boost=True, bot_type="crypto") is True


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
