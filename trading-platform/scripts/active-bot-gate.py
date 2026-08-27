#!/usr/bin/env python3
"""Compute active-bot profitability gate from live production APIs."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DASHBOARD = "https://apex-trading-dashboard-flame.vercel.app"
MIN_TRADES = 100
MIN_WIN_RATE = 0.55
MIN_PROFIT_FACTOR = 1.3
MIN_DAYS = 30


def fetch(path: str) -> dict | list:
    with urllib.request.urlopen(f"{DASHBOARD}/api/backend/{path}", timeout=45) as resp:
        return json.load(resp)


def fetch_active_gate() -> dict | None:
    """Use dashboard /api/active-gate when deployed (PR #52+)."""
    try:
        with urllib.request.urlopen(f"{DASHBOARD}/api/active-gate", timeout=45) as resp:
            data = json.load(resp)
            if data.get("active_bots") and "error" not in data:
                return data
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            print(f"active-gate HTTP {exc.code}, falling back", file=sys.stderr)
    except Exception as exc:
        print(f"active-gate unavailable ({exc}), falling back", file=sys.stderr)
    return None


def aggregate_win_rate(sells: list[dict]) -> float:
    winners = sum(1 for t in sells if t.get("is_winner") is True)
    losers = sum(1 for t in sells if t.get("is_winner") is False)
    decided = winners + losers
    return winners / decided if decided else 0.0


def profit_factor(sells: list[dict]) -> float | None:
    winners = [t for t in sells if t.get("is_winner") is True]
    losers = [t for t in sells if t.get("is_winner") is False]
    gross_profit = sum(t.get("pnl", 0) for t in winners)
    gross_loss = abs(sum(t.get("pnl", 0) for t in losers))
    if gross_loss <= 0:
        return gross_profit if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def infer_paused_bots(strategies: list[dict]) -> list[str]:
    return [s["bot_type"] for s in strategies if s.get("max_position_pct", 1) <= 0]


def compute_local() -> dict:
    api = fetch("profitability")
    strategies = fetch("strategies")
    portfolios = fetch("portfolios")
    trades = fetch("trades?limit=200")

    paused = api.get("paused_bots") or infer_paused_bots(strategies)
    paused_set = set(paused)
    sells = [t for t in trades if t.get("action") == "sell" and t.get("bot_type") not in paused_set]
    active_portfolios = [p for p in portfolios if p.get("bot_type") not in paused_set]

    win_rate = aggregate_win_rate(sells)
    pf = profit_factor(sells)
    total_pnl = sum(p.get("total_pnl", 0) for p in active_portfolios)
    total_trades = len(sells)
    days = api.get("days_trading") or 0
    verification_day = api.get("verification_day") or days + 1

    live_ready = (
        total_trades >= MIN_TRADES
        and win_rate >= MIN_WIN_RATE
        and pf is not None
        and pf >= MIN_PROFIT_FACTOR
        and total_pnl > 0
        and days >= MIN_DAYS
    )

    return {
        "paused_bots": paused,
        "active_bots": {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 4),
            "profit_factor": round(pf, 2) if pf is not None else pf,
            "total_pnl": round(total_pnl, 2),
        },
        "aggregate": {
            "total_trades": api.get("total_trades"),
            "win_rate": api.get("win_rate"),
            "profit_factor": api.get("profit_factor"),
            "total_pnl": api.get("total_pnl"),
        },
        "verification_day": verification_day,
        "live_trading_ready": live_ready,
    }


def main() -> int:
    out = fetch_active_gate() or compute_local()

    print(json.dumps(out, indent=2))

    active = out["active_bots"]
    total_trades = active["total_trades"]
    win_rate = active["win_rate"]
    pf = active.get("profit_factor")
    total_pnl = active["total_pnl"]
    verification_day = out.get("verification_day", "?")

    pf_label = f"{pf:.2f}" if pf is not None else "n/a"
    print(
        f"\nActive bots: {total_trades} trades | WR {win_rate*100:.1f}% | "
        f"PF {pf_label} | PnL ${total_pnl:.2f} | day {verification_day}/30",
        file=sys.stderr,
    )
    if out.get("paused_bots"):
        print(f"Excludes paused: {', '.join(out['paused_bots'])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
