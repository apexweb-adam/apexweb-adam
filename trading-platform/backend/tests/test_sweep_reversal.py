import pandas as pd

from app.engines.sweep_reversal import (
  DOM_AVAILABLE,
  RISK_USD,
  SLEEVE_ID,
  detect_sweep_reversal,
)


def _flat(rows: int = 30, volume: float = 1_000_000.0) -> pd.DataFrame:
  return pd.DataFrame({
    "open": [100.0] * rows,
    "high": [101.0] * rows,
    "low": [99.0] * rows,
    "close": [100.0] * rows,
    "volume": [volume] * rows,
  })


def _bullish_sweep() -> pd.DataFrame:
  df = _flat()
  df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
    100.2, 101.0, 97.0, 100.2, 3_000_000.0,
  ]
  df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
    100.4, 102.5, 100.3, 102.2, 1_000_000.0,
  ]
  return df


def _bearish_sweep() -> pd.DataFrame:
  df = _flat()
  df.loc[df.index[-2], ["open", "high", "low", "close", "volume"]] = [
    99.8, 103.5, 99.0, 99.8, 3_000_000.0,
  ]
  df.loc[df.index[-1], ["open", "high", "low", "close", "volume"]] = [
    99.6, 99.9, 97.5, 97.8, 1_000_000.0,
  ]
  return df


def test_insufficient_bars_hold():
  signal = detect_sweep_reversal(_flat(rows=5), symbol="MES")
  assert signal.sleeve_id == SLEEVE_ID
  assert signal.direction == "hold"
  assert signal.paper_only is True
  assert signal.risk_usd == RISK_USD
  assert signal.dom_available is DOM_AVAILABLE
  assert "insufficient" in signal.reason


def test_bullish_sweep_reclaim_bos_and_absorption_proxy():
  signal = detect_sweep_reversal(_bullish_sweep(), symbol="MES")
  assert signal.direction == "buy"
  assert signal.reclaim is True
  assert signal.structure_confirmed is True
  assert signal.volume_climax is True
  assert signal.hidden_liquidity == "bid"
  assert signal.absorption_score >= 0.55
  assert signal.swept_level == 99.0
  assert signal.dom_available is False
  assert signal.paper_only is True
  assert signal.risk_usd == 400.0
  assert "No DOM" in signal.reason


def test_no_volume_climax_does_not_trade():
  df = _bullish_sweep()
  df.loc[df.index[-2], "volume"] = 1_000_000.0
  signal = detect_sweep_reversal(df, symbol="ES")
  assert signal.direction == "hold"
  assert signal.volume_climax is False
  assert signal.hidden_liquidity == "none"
  assert "no volume climax" in signal.reason


def test_sweep_without_reclaim_holds():
  df = _bullish_sweep()
  df.loc[df.index[-2], "close"] = 96.5
  df.loc[df.index[-1], "close"] = 96.8
  signal = detect_sweep_reversal(df, symbol="ES")
  assert signal.direction == "hold"
  assert signal.reclaim is False


def test_reclaim_without_structure_holds():
  df = _bullish_sweep()
  df.loc[df.index[-1], ["high", "close"]] = [100.6, 100.4]
  signal = detect_sweep_reversal(df, symbol="NQ")
  assert signal.direction == "hold"
  assert signal.reclaim is True
  assert signal.structure_confirmed is False


def test_bearish_sweep_marks_hidden_offer():
  signal = detect_sweep_reversal(_bearish_sweep(), symbol="MNQ")
  assert signal.direction == "sell"
  assert signal.hidden_liquidity == "offer"
  assert signal.swept_level == 101.0
  assert signal.structure_confirmed is True
  assert signal.dom_available is False
  assert "No DOM" in signal.reason
