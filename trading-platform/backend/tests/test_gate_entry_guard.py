"""Tests for gate entry tightening helpers."""

import pytest

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
  assert in_shadow_graduation_nudge("commodities", 0.47) is True
  assert in_shadow_graduation_nudge("commodities", 0.45) is True
  assert in_shadow_graduation_nudge("commodities", 0.43) is False
  assert in_shadow_graduation_nudge("commodities", 0.40) is False
  assert in_shadow_graduation_nudge("crypto", 0.46) is True
  assert in_shadow_graduation_nudge("crypto", 0.44) is True
  assert in_shadow_graduation_nudge("crypto", 0.42) is True
  assert in_shadow_graduation_nudge("crypto", 0.41) is False
  assert in_shadow_graduation_nudge("crypto", 0.42, profit_factor=1.1, total_pnl=5.0) is True
  assert in_shadow_graduation_nudge("crypto", 0.41, profit_factor=1.1, total_pnl=5.0) is False
  assert in_shadow_graduation_nudge("crypto", 0.42, profit_factor=0.98, total_pnl=5.0) is True
  assert in_shadow_graduation_nudge("commodities", 0.44, profit_factor=1.19, total_pnl=19.0) is True
  assert in_shadow_graduation_nudge("commodities", 0.42, profit_factor=1.19, total_pnl=19.0) is True
  assert in_shadow_graduation_nudge("commodities", 0.41, profit_factor=1.19, total_pnl=19.0) is False
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
    composite=0.50,
    entry_min_signal=0.31,
    integration_boost=0.0,
  ) is True
  assert shadow_intel_composite_override(
    "commodities",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.46,
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
    composite=0.48,
    entry_min_signal=0.26,
    integration_boost=0.0,
  ) is True
  assert shadow_intel_composite_override(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.44,
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


def test_whale_memecoin_aligned():
  from app.engines.gate_entry_guard import whale_memecoin_aligned

  assert whale_memecoin_aligned(
    "wallet tracker:+0.45; dexscreener:+0.35", 0.12
  ) is True
  assert whale_memecoin_aligned("hyperliquid:+0.20; wallet tracker:+0.40", 0.11) is True
  assert whale_memecoin_aligned("wallet tracker:+0.45", 0.12) is False
  assert whale_memecoin_aligned("dexscreener:+0.35", 0.12) is False


def test_shadow_intel_composite_override_whale_aligned_crypto():
  assert shadow_intel_composite_override(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    composite=0.41,
    entry_min_signal=0.26,
    integration_boost=0.14,
    whale_aligned=True,
  ) is True


def test_stocks_negative_pf_blocks_entry():
  from app.engines.gate_entry_guard import stocks_negative_pf_blocks_entry

  assert stocks_negative_pf_blocks_entry(
    bot_type="stocks_futures",
    symbol="TSLA",
    composite=0.35,
    proven_winners=frozenset({"NVDA"}),
    profit_factor=0.62,
    total_trades=15,
  ) is True
  assert stocks_negative_pf_blocks_entry(
    bot_type="stocks_futures",
    symbol="NVDA",
    composite=0.45,
    proven_winners=frozenset({"NVDA"}),
    profit_factor=0.62,
    total_trades=15,
  ) is False
  assert stocks_negative_pf_blocks_entry(
    bot_type="stocks_futures",
    symbol="NVDA",
    composite=0.39,
    proven_winners=frozenset({"NVDA"}),
    profit_factor=0.62,
    total_trades=15,
    bot_win_rate=0.571,
  ) is False
  assert stocks_negative_pf_blocks_entry(
    bot_type="stocks_futures",
    symbol="NVDA",
    composite=0.39,
    proven_winners=frozenset({"NVDA"}),
    profit_factor=0.62,
    total_trades=15,
    bot_win_rate=0.50,
  ) is True
  assert stocks_negative_pf_blocks_entry(
    bot_type="crypto",
    symbol="BTCUSDT",
    composite=0.35,
    proven_winners=frozenset(),
    profit_factor=0.62,
    total_trades=15,
  ) is False


def test_graduation_nudge_easing_active_for_active_commodities():
  from app.engines.gate_entry_guard import (
    graduation_nudge_easing_active,
    hard_skip_blocks_shadow_entry,
    shadow_intel_composite_override,
  )

  assert graduation_nudge_easing_active(
    "commodities",
    graduation_nudge=True,
    shadow_mode=False,
  )
  assert not graduation_nudge_easing_active(
    "crypto",
    graduation_nudge=True,
    shadow_mode=False,
  )
  assert shadow_intel_composite_override(
    "commodities",
    graduation_nudge=True,
    shadow_mode=False,
    composite=0.50,
    entry_min_signal=0.31,
    integration_boost=0.0,
  )
  assert not hard_skip_blocks_shadow_entry(
    "SI=F",
    bot_type="commodities",
    recent_skip=frozenset(),
    large_skip=frozenset({"SI=F"}),
    review_skip=frozenset(),
    graduation_nudge=True,
    shadow_mode=False,
    intel_override=False,
    composite=0.50,
    integration_boost=0.0,
  )


def test_chronic_loser_blocks_shadow_entry_intel_bypass():
  from app.engines.gate_entry_guard import (
    chronic_loser_blocks_shadow_entry,
    shadow_chronic_position_scale,
  )

  assert chronic_loser_blocks_shadow_entry(
    "BTCUSDT",
    frozenset({"BTCUSDT"}),
    bot_type="crypto",
    graduation_nudge=True,
    shadow_mode=True,
    intel_override=True,
  ) is False
  assert chronic_loser_blocks_shadow_entry(
    "BTCUSDT",
    frozenset({"BTCUSDT"}),
    bot_type="crypto",
    graduation_nudge=True,
    shadow_mode=True,
    intel_override=False,
  ) is True
  assert chronic_loser_blocks_shadow_entry(
    "NVDA",
    frozenset({"NVDA"}),
    bot_type="stocks_futures",
    graduation_nudge=False,
    shadow_mode=False,
    intel_override=True,
  ) is True
  assert shadow_chronic_position_scale(
    "SI=F",
    frozenset({"SI=F"}),
    graduation_nudge=True,
    shadow_mode=True,
    intel_override=True,
  ) == 0.25
  assert shadow_chronic_position_scale(
    "SI=F",
    frozenset({"SI=F"}),
    graduation_nudge=True,
    shadow_mode=True,
    intel_override=False,
  ) == 1.0


def test_shadow_graduation_min_hold_seconds():
  from app.engines.gate_entry_guard import shadow_graduation_min_hold_seconds

  assert shadow_graduation_min_hold_seconds(
    "crypto", graduation_nudge=True, shadow_mode=True, default_seconds=300
  ) == 900
  assert shadow_graduation_min_hold_seconds(
    "crypto", graduation_nudge=False, shadow_mode=True, default_seconds=300
  ) == 300
  assert shadow_graduation_min_hold_seconds(
    "commodities", graduation_nudge=True, shadow_mode=True, default_seconds=180
  ) == 600
  assert shadow_graduation_min_hold_seconds(
    "commodities", graduation_nudge=True, shadow_mode=False, default_seconds=180
  ) == 600


def test_shadow_graduation_min_composite():
  from app.engines.gate_entry_guard import shadow_graduation_min_composite

  assert shadow_graduation_min_composite(
    "crypto", graduation_nudge=True, shadow_mode=True
  ) == 0.26
  assert shadow_graduation_min_composite(
    "commodities", graduation_nudge=True, shadow_mode=False
  ) == 0.28
  assert shadow_graduation_min_composite(
    "crypto", graduation_nudge=False, shadow_mode=True
  ) is None


def test_bot_win_rate_for_graduation_nudge_active_commodities():
  from app.engines.gate_entry_guard import (
    bot_win_rate_for_graduation_nudge,
    in_shadow_graduation_nudge,
  )

  wr = bot_win_rate_for_graduation_nudge(
    "commodities",
    shadow_mode=False,
    shadow_bot_wr=None,
    per_bot_stats={"win_rate": 0.444, "profit_factor": 1.19, "total_pnl": 19.13},
  )
  assert wr == 0.444
  assert in_shadow_graduation_nudge(
    "commodities",
    wr,
    profit_factor=1.19,
    total_pnl=19.13,
  )


def test_shadow_graduation_exits_active_wr_buffer():
  from app.engines.gate_entry_guard import shadow_graduation_exits_active

  assert shadow_graduation_exits_active(
    "crypto",
    graduation_nudge=False,
    shadow_mode=True,
    bot_win_rate=0.418,
  ) is True
  assert shadow_graduation_exits_active(
    "crypto",
    graduation_nudge=False,
    shadow_mode=True,
    bot_win_rate=0.38,
  ) is False


def test_shadow_graduation_loss_exposure_blocks_entry():
  from types import SimpleNamespace

  from app.engines.gate_entry_guard import shadow_graduation_loss_exposure_blocks_entry

  losers = [
    SimpleNamespace(unrealized_pnl=-3.5),
    SimpleNamespace(unrealized_pnl=-3.2),
  ]
  assert shadow_graduation_loss_exposure_blocks_entry(
    losers, graduation_nudge=True, shadow_mode=True
  ) is True
  assert shadow_graduation_loss_exposure_blocks_entry(
    losers, graduation_nudge=True, shadow_mode=False
  ) is False
  assert shadow_graduation_loss_exposure_blocks_entry(
    [SimpleNamespace(unrealized_pnl=-1.0)], graduation_nudge=True, shadow_mode=True
  ) is False
  assert shadow_graduation_loss_exposure_blocks_entry(
    [SimpleNamespace(unrealized_pnl=-2.6)], graduation_nudge=True, shadow_mode=True
  ) is True
  assert shadow_graduation_loss_exposure_blocks_entry(
    [SimpleNamespace(unrealized_pnl=-4.2)], graduation_nudge=True, shadow_mode=True
  ) is True


def test_shadow_graduation_loss_wind_down():
  from app.engines.gate_entry_guard import shadow_graduation_loss_wind_down

  assert shadow_graduation_loss_wind_down(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=-4.0,
    held_seconds=900,
    min_hold_seconds=900,
  ) is True
  assert shadow_graduation_loss_wind_down(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=-1.5,
    held_seconds=900,
    min_hold_seconds=900,
  ) is False
  assert shadow_graduation_loss_wind_down(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=-2.0,
    held_seconds=600,
    min_hold_seconds=900,
  ) is False
  assert shadow_graduation_loss_wind_down(
    graduation_nudge=False,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=-2.0,
    held_seconds=900,
    min_hold_seconds=900,
  ) is False
  assert shadow_graduation_loss_wind_down(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="stocks_futures",
    unrealized=-2.0,
    held_seconds=900,
    min_hold_seconds=900,
  ) is False


def test_shadow_graduation_loss_wind_down_profitable_nudge_threshold():
  from app.engines.gate_entry_guard import shadow_graduation_loss_wind_down

  assert shadow_graduation_loss_wind_down(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=-1.5,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.45,
    profit_factor=1.11,
    total_pnl=10.0,
  ) is False
  assert shadow_graduation_loss_wind_down(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=-4.0,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.45,
    profit_factor=1.11,
    total_pnl=10.0,
  ) is True
  assert shadow_graduation_loss_wind_down(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=-3.5,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.45,
    profit_factor=1.11,
    total_pnl=10.0,
  ) is False


def test_active_gate_uses_tighter_exit_thresholds():
  from app.engines.gate_entry_guard import (
    shadow_graduation_loss_wind_down,
    shadow_graduation_profit_lock,
  )

  profitable = dict(
    graduation_nudge=True,
    bot_type="commodities",
    held_seconds=900,
    min_hold_seconds=600,
    bot_win_rate=0.444,
    profit_factor=1.19,
    total_pnl=19.13,
  )
  assert shadow_graduation_loss_wind_down(
    shadow_mode=False,
    unrealized=-4.0,
    **profitable,
  ) is True
  assert shadow_graduation_loss_wind_down(
    shadow_mode=True,
    unrealized=-3.5,
    **profitable,
  ) is False
  assert shadow_graduation_loss_wind_down(
    shadow_mode=True,
    unrealized=-4.5,
    **profitable,
  ) is True
  assert shadow_graduation_profit_lock(
    shadow_mode=False,
    unrealized=3.1,
    **profitable,
  ) is True
  assert shadow_graduation_profit_lock(
    shadow_mode=True,
    unrealized=3.1,
    **profitable,
  ) is False


def test_shadow_graduation_profit_lock():
  from app.engines.gate_entry_guard import shadow_graduation_profit_lock

  assert shadow_graduation_profit_lock(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=5.0,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.45,
    profit_factor=0.98,
    total_pnl=10.0,
  ) is True
  assert shadow_graduation_profit_lock(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=3.6,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.45,
    profit_factor=1.02,
    total_pnl=10.0,
  ) is True
  assert shadow_graduation_profit_lock(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=3.0,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.45,
    profit_factor=0.98,
    total_pnl=10.0,
  ) is False
  assert shadow_graduation_profit_lock(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=3.0,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.423,
    profit_factor=0.98,
    total_pnl=-1.89,
  ) is True
  assert shadow_graduation_profit_lock(
    graduation_nudge=True,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=2.5,
    held_seconds=900,
    min_hold_seconds=900,
    bot_win_rate=0.423,
    profit_factor=0.98,
    total_pnl=-1.89,
  ) is False
  assert shadow_graduation_profit_lock(
    graduation_nudge=True,
    shadow_mode=False,
    bot_type="commodities",
    unrealized=4.5,
    held_seconds=600,
    min_hold_seconds=600,
    bot_win_rate=0.444,
    profit_factor=1.19,
    total_pnl=19.13,
  ) is True
  assert shadow_graduation_profit_lock(
    graduation_nudge=False,
    shadow_mode=True,
    bot_type="crypto",
    unrealized=10.0,
    held_seconds=900,
    min_hold_seconds=900,
  ) is False


def test_early_verification_macd_ok():
  from app.engines.gate_entry_guard import early_verification_macd_ok

  assert early_verification_macd_ok(macd_signal="bullish", integration_boost=0.0) is True
  assert early_verification_macd_ok(macd_signal="bearish", integration_boost=0.10) is True
  assert early_verification_macd_ok(macd_signal="bearish", integration_boost=0.02) is False


def test_stocks_session_close_wind_down():
  from app.engines.gate_entry_guard import stocks_session_close_wind_down

  assert stocks_session_close_wind_down(
    in_session=False,
    minutes_until_close=None,
    unrealized=5.0,
    signal_direction="buy",
  ) is True
  assert stocks_session_close_wind_down(
    in_session=True,
    minutes_until_close=10,
    unrealized=5.0,
    signal_direction="buy",
  ) is True
  assert stocks_session_close_wind_down(
    in_session=True,
    minutes_until_close=25,
    unrealized=-2.0,
    signal_direction="buy",
  ) is True
  assert stocks_session_close_wind_down(
    in_session=True,
    minutes_until_close=25,
    unrealized=2.0,
    signal_direction="buy",
  ) is True
  assert stocks_session_close_wind_down(
    in_session=True,
    minutes_until_close=45,
    unrealized=-2.0,
    signal_direction="buy",
  ) is False


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


def test_intel_override_allows_long_entry_blocks_bearish_commodities():
  from app.engines.gate_entry_guard import intel_override_allows_long_entry

  assert intel_override_allows_long_entry(
    "commodities",
    intel_override=True,
    signal_direction="sell",
    shadow_mode=False,
    graduation_nudge=True,
  ) is False
  assert intel_override_allows_long_entry(
    "crypto",
    intel_override=True,
    signal_direction="sell",
    shadow_mode=True,
    graduation_nudge=True,
  ) is True
  assert intel_override_allows_long_entry(
    "commodities",
    intel_override=True,
    signal_direction="sell",
    shadow_mode=True,
    graduation_nudge=True,
  ) is True
  assert intel_override_allows_long_entry(
    "commodities",
    intel_override=True,
    signal_direction="buy",
    shadow_mode=False,
    graduation_nudge=True,
  ) is True


def test_graduation_nudge_min_sentiment_eases_shadow_crypto():
  from app.engines.gate_entry_guard import graduation_nudge_min_sentiment

  eased = graduation_nudge_min_sentiment(
    "crypto",
    0.10,
    graduation_nudge=True,
    shadow_mode=True,
  )
  assert eased == pytest.approx(0.06)


def test_commodities_graduation_entry_min_signal_bullish_ease():
  from app.engines.gate_entry_guard import commodities_graduation_entry_min_signal

  eased = commodities_graduation_entry_min_signal(
    0.31,
    bot_type="commodities",
    graduation_nudge=True,
    shadow_mode=False,
    signal_direction="buy",
    macd_signal="bullish",
    symbol="NG=F",
    proven_winners=frozenset(),
  )
  assert eased == 0.22


def test_commodities_graduation_entry_min_signal_proven_winner_active_gate():
  from app.engines.gate_entry_guard import commodities_graduation_entry_min_signal

  eased = commodities_graduation_entry_min_signal(
    0.31,
    bot_type="commodities",
    graduation_nudge=True,
    shadow_mode=False,
    signal_direction="buy",
    macd_signal="bullish",
    symbol="CL=F",
    proven_winners=frozenset({"CL=F"}),
  )
  assert eased == pytest.approx(0.14)


def test_graduation_nudge_sentiment_ok_commodities_proven_winner_active_gate():
  from app.engines.gate_entry_guard import graduation_nudge_sentiment_ok

  assert graduation_nudge_sentiment_ok(
    "commodities",
    graduation_nudge=True,
    shadow_mode=False,
    sentiment=0.02,
    integration_boost=0.0,
    min_sentiment=0.06,
    composite=0.136,
    entry_min_signal=0.12,
    signal_direction="buy",
    macd_signal="bullish",
    symbol="CL=F",
    proven_winners=frozenset({"CL=F"}),
  ) is True
  assert graduation_nudge_sentiment_ok(
    "commodities",
    graduation_nudge=True,
    shadow_mode=False,
    sentiment=0.02,
    integration_boost=0.0,
    min_sentiment=0.06,
    composite=0.10,
    entry_min_signal=0.12,
    signal_direction="buy",
    macd_signal="bullish",
    symbol="CL=F",
    proven_winners=frozenset({"CL=F"}),
  ) is False


def test_crypto_graduation_entry_min_signal_bullish_ease():
  from app.engines.gate_entry_guard import crypto_graduation_entry_min_signal

  eased = crypto_graduation_entry_min_signal(
    0.302,
    bot_type="crypto",
    graduation_nudge=True,
    shadow_mode=True,
    signal_direction="buy",
    macd_signal="bullish",
  )
  assert eased == 0.242


def test_graduation_nudge_sentiment_ok_shadow_crypto_composite_bypass():
  from app.engines.gate_entry_guard import graduation_nudge_sentiment_ok

  assert graduation_nudge_sentiment_ok(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    sentiment=-0.5,
    integration_boost=0.0,
    min_sentiment=0.06,
    composite=0.311,
    entry_min_signal=0.30,
  ) is True
  assert graduation_nudge_sentiment_ok(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    sentiment=-0.5,
    integration_boost=0.0,
    min_sentiment=0.06,
    composite=0.295,
    entry_min_signal=0.30,
    signal_direction="sell",
    macd_signal="bearish",
  ) is False
  assert graduation_nudge_sentiment_ok(
    "crypto",
    graduation_nudge=True,
    shadow_mode=True,
    sentiment=-0.197,
    integration_boost=0.0,
    min_sentiment=0.06,
    composite=0.267,
    entry_min_signal=0.26,
    signal_direction="buy",
    macd_signal="bullish",
  ) is True


def test_open_position_cap_blocks_shadow_not_gate_tightening():
  from app.engines.gate_entry_guard import GateEntryTightening, open_position_cap_blocks_entry

  tightening = GateEntryTightening(
    active=True,
    win_rate=0.44,
    min_sentiment=0.04,
    require_macd_bullish=True,
    min_composite_boost=0.04,
    max_crypto_open_positions=1,
  )
  assert open_position_cap_blocks_entry(
    "crypto",
    shadow_mode=True,
    open_count=1,
    gate_tightening=tightening,
    shadow_open_cap=3,
  ) is False
  assert open_position_cap_blocks_entry(
    "crypto",
    shadow_mode=True,
    open_count=3,
    gate_tightening=tightening,
    shadow_open_cap=3,
  ) is True
  assert open_position_cap_blocks_entry(
    "crypto",
    shadow_mode=False,
    open_count=1,
    gate_tightening=tightening,
    shadow_open_cap=None,
  ) is True


def test_apply_gate_tightening_skips_loss_streak_during_graduation_nudge():
  from app.engines.gate_entry_guard import apply_gate_tightening_min_signal

  tightening = GateEntryTightening(
    active=True,
    win_rate=0.44,
    min_sentiment=0.04,
    require_macd_bullish=True,
    min_composite_boost=0.04,
  )
  base = apply_gate_tightening_min_signal(
    0.31,
    "commodities",
    gate_tightening=tightening,
    graduation_nudge=False,
    shadow_mode=False,
    loss_streak=3,
  )
  eased = apply_gate_tightening_min_signal(
    0.31,
    "commodities",
    gate_tightening=tightening,
    graduation_nudge=True,
    shadow_mode=False,
    loss_streak=3,
  )
  assert base == pytest.approx(0.43)
  assert eased == pytest.approx(0.31)


def test_gate_cap_pressure_proxy_wind_down_at_cap():
  from app.engines.gate_entry_guard import gate_cap_pressure_proxy_wind_down

  tightening = GateEntryTightening(
    active=False,
    win_rate=0.444,
    min_sentiment=0.0,
    require_macd_bullish=False,
    min_composite_boost=0.0,
    max_commodities_open_positions=3,
  )
  base = dict(
    bot_type="commodities",
    shadow_mode=False,
    graduation_nudge=True,
    symbol="XAUUSDT",
    held_seconds=600,
    min_hold_seconds=180,
    open_count=3,
    gate_tightening=tightening,
  )
  assert gate_cap_pressure_proxy_wind_down(unrealized=-0.80, **base) is True
  assert gate_cap_pressure_proxy_wind_down(unrealized=-0.27, **base) is True
  assert gate_cap_pressure_proxy_wind_down(unrealized=0.0, **base) is False
  assert gate_cap_pressure_proxy_wind_down(unrealized=0.50, **base) is False
  assert gate_cap_pressure_proxy_wind_down(
    unrealized=-0.80,
    open_count=2,
    bot_type="commodities",
    shadow_mode=False,
    graduation_nudge=True,
    symbol="XAUUSDT",
    held_seconds=600,
    min_hold_seconds=180,
    gate_tightening=tightening,
  ) is False
  assert gate_cap_pressure_proxy_wind_down(
    unrealized=-0.80,
    bot_type="commodities",
    shadow_mode=True,
    graduation_nudge=True,
    symbol="XAUUSDT",
    held_seconds=600,
    min_hold_seconds=180,
    open_count=3,
    gate_tightening=tightening,
  ) is False
  assert gate_cap_pressure_proxy_wind_down(
    unrealized=-0.80,
    bot_type="commodities",
    shadow_mode=False,
    graduation_nudge=True,
    symbol="CL=F",
    held_seconds=600,
    min_hold_seconds=180,
    open_count=3,
    gate_tightening=tightening,
  ) is False
