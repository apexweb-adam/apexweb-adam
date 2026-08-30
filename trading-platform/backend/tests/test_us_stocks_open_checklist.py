"""Tests for US stocks open checklist builder."""

from app.engines.us_stocks_open_checklist import (
  build_us_stocks_open_checks,
  format_us_stocks_checklist_crm_html,
  should_show_us_stocks_checklist_on_crm,
)


def test_build_us_stocks_open_checks_preflight_pass():
  checks = build_us_stocks_open_checks(
    platform_revision_current=True,
    minutes_until_open=1800,
    prep_phase="extended",
    in_session=False,
    auto_entry_queued=True,
    open_ready_symbols=["AAPL"],
    near_floor_symbols=[],
    stocks_paused=False,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=False,
    open_ready_below_floor=[],
    phase="preflight",
  )
  assert any(c["id"] == "auto_entry_queued" and c["status"] == "pass" for c in checks)


def test_build_us_stocks_open_checks_shadow_mode_with_auto_entry_warns():
  checks = build_us_stocks_open_checks(
    platform_revision_current=True,
    minutes_until_open=1800,
    prep_phase="extended",
    in_session=False,
    auto_entry_queued=True,
    open_ready_symbols=["AAPL"],
    near_floor_symbols=[],
    stocks_paused=True,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=False,
    open_ready_below_floor=[],
    phase="preflight",
  )
  active = next(c for c in checks if c["id"] == "stocks_active")
  assert active["status"] == "warn"
  assert active["critical"] is False
  assert "AAPL" in active["message"]


def test_should_show_us_stocks_checklist_when_aapl_queued():
  assert should_show_us_stocks_checklist_on_crm(
    {
      "minutes_until_open": 1800,
      "open_ready": {"symbols": ["AAPL"]},
    }
  )


def test_format_us_stocks_checklist_crm_html_near_floor_sticky():
  html = format_us_stocks_checklist_crm_html(
    {
      "phase": "preflight",
      "ready": True,
      "minutes_until_open": 1800,
      "open_ready": {
        "symbols": ["AAPL"],
        "composite_floor": 0.34,
        "sticky_symbols": ["AAPL"],
        "release_margin": 0.02,
      },
      "near_floor": {
        "symbols": ["NVDA"],
        "details": [{"symbol": "NVDA", "gap_to_floor": 0.02}],
      },
      "checks": [{"id": "auto_entry_queued", "status": "pass", "message": "AAPL queued"}],
    }
  )
  assert "sticky AAPL" in html
  assert "near floor NVDA +0.02" in html


def test_format_us_stocks_checklist_crm_html():
  html = format_us_stocks_checklist_crm_html(
    {
      "phase": "preflight",
      "ready": True,
      "minutes_until_open": 1800,
      "open_ready": {"symbols": ["AAPL"], "composite_floor": 0.34},
      "checks": [{"id": "auto_entry_queued", "status": "pass", "message": "AAPL queued"}],
    }
  )
  assert "US stocks open checklist" in html
  assert "AAPL" in html
