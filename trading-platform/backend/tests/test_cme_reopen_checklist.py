"""Tests for CME reopen checklist builder."""

from app.engines.cme_reopen_checklist import (
  build_cme_reopen_checks,
  _symbols_below_floor,
)
from app.engines.gate_entry_guard import OPEN_READY_QUEUE_RELEASE_MARGIN


def test_symbols_below_floor_honors_sticky_release_margin():
  sticky = [{"symbol": "NG=F", "composite": 0.418, "sticky_queue": True}]
  assert _symbols_below_floor(
    sticky,
    0.42,
    release_margin=OPEN_READY_QUEUE_RELEASE_MARGIN,
  ) == []
  below = [{"symbol": "NG=F", "composite": 0.39, "sticky_queue": True}]
  assert _symbols_below_floor(
    below,
    0.42,
    release_margin=OPEN_READY_QUEUE_RELEASE_MARGIN,
  ) == ["NG=F"]
  fresh = [{"symbol": "CL=F", "composite": 0.418, "sticky_queue": False}]
  assert _symbols_below_floor(fresh, 0.42) == ["CL=F"]


def test_symbols_below_floor_honors_extended_sticky_margin():
  from app.engines.gate_entry_guard import OPEN_READY_QUEUE_EXTENDED_MARGIN

  extended = [
    {"symbol": "NG=F", "composite": 0.376, "sticky_queue": True, "extended_sticky": True},
  ]
  assert _symbols_below_floor(
    extended,
    0.42,
    release_margin=OPEN_READY_QUEUE_RELEASE_MARGIN,
    extended_margin=OPEN_READY_QUEUE_EXTENDED_MARGIN,
  ) == []
  too_low = [
    {"symbol": "NG=F", "composite": 0.35, "sticky_queue": True, "extended_sticky": True},
  ]
  assert _symbols_below_floor(
    too_low,
    0.42,
    release_margin=OPEN_READY_QUEUE_RELEASE_MARGIN,
    extended_margin=OPEN_READY_QUEUE_EXTENDED_MARGIN,
  ) == ["NG=F"]


def test_build_cme_reopen_checks_preflight_pass():
  checks = build_cme_reopen_checks(
    platform_revision_current=True,
    minutes_until_open=900,
    prep_phase="extended",
    in_session=False,
    auto_entry_queued=True,
    open_ready_symbols=["NG=F", "CL=F"],
    near_floor_symbols=[],
    commodities_paused=False,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=False,
    composite_floor=0.42,
    open_ready_below_floor=[],
    phase="preflight",
  )
  assert any(c["id"] == "auto_entry_queued" and c["status"] == "pass" for c in checks)
  assert all(c["status"] != "fail" for c in checks if c.get("critical"))


def test_build_cme_reopen_checks_skips_near_floor_warn_when_symbol_queued():
  checks = build_cme_reopen_checks(
    platform_revision_current=True,
    minutes_until_open=900,
    prep_phase="extended",
    in_session=False,
    auto_entry_queued=True,
    open_ready_symbols=["NG=F"],
    near_floor_symbols=["NG=F"],
    commodities_paused=False,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=False,
    composite_floor=0.42,
    open_ready_below_floor=[],
    phase="preflight",
  )
  floor = next(c for c in checks if c["id"] == "composite_floor")
  assert floor["status"] == "pass"


def test_build_cme_reopen_checks_deploy_behind_critical_near_open():
  checks = build_cme_reopen_checks(
    platform_revision_current=False,
    minutes_until_open=120,
    prep_phase="imminent",
    in_session=False,
    auto_entry_queued=True,
    open_ready_symbols=["NG=F"],
    near_floor_symbols=[],
    commodities_paused=False,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=False,
    composite_floor=0.42,
    open_ready_below_floor=[],
    phase="preflight",
  )
  deploy = next(c for c in checks if c["id"] == "deploy_current")
  assert deploy["status"] == "fail"
  assert deploy["critical"] is True


def test_build_cme_reopen_checks_post_open_requires_burst_scan():
  checks = build_cme_reopen_checks(
    platform_revision_current=True,
    minutes_until_open=0,
    prep_phase="open",
    in_session=True,
    auto_entry_queued=True,
    open_ready_symbols=["NG=F"],
    near_floor_symbols=[],
    commodities_paused=False,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=False,
    composite_floor=0.42,
    open_ready_below_floor=[],
    phase="post_open",
  )
  burst = next(c for c in checks if c["id"] == "burst_scan_logged")
  assert burst["status"] == "fail"


def test_build_cme_reopen_checks_post_open_auto_entry_satisfies_burst():
  checks = build_cme_reopen_checks(
    platform_revision_current=True,
    minutes_until_open=0,
    prep_phase="open",
    in_session=True,
    auto_entry_queued=False,
    open_ready_symbols=[],
    near_floor_symbols=[],
    commodities_paused=False,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=True,
    composite_floor=0.42,
    open_ready_below_floor=[],
    phase="post_open",
  )
  burst = next(c for c in checks if c["id"] == "burst_scan_logged")
  assert burst["status"] == "pass"


def test_build_cme_reopen_checks_shadow_mode_with_auto_entry_warns():
  checks = build_cme_reopen_checks(
    platform_revision_current=True,
    minutes_until_open=180,
    prep_phase="extended",
    in_session=False,
    auto_entry_queued=True,
    open_ready_symbols=["NG=F"],
    near_floor_symbols=[],
    commodities_paused=True,
    bots_running=4,
    has_burst_scan=False,
    has_auto_entry=False,
    composite_floor=0.42,
    open_ready_below_floor=[],
    phase="preflight",
  )
  active = next(c for c in checks if c["id"] == "commodities_active")
  assert active["status"] == "warn"
  assert active["critical"] is False


def test_format_cme_checklist_crm_html():
  from app.engines.cme_reopen_checklist import format_cme_checklist_crm_html

  html = format_cme_checklist_crm_html(
    {
      "phase": "preflight",
      "ready": True,
      "minutes_until_open": 900,
      "open_ready": {"symbols": ["NG=F"], "composite_floor": 0.42},
      "near_floor": {
        "symbols": ["CL=F"],
        "details": [{"symbol": "CL=F", "gap_to_floor": 0.014}],
      },
      "checks": [
        {"id": "auto_entry_queued", "status": "pass", "message": "queued NG=F"},
      ],
    }
  )
  assert "CME reopen checklist" in html
  assert "auto_entry_queued" in html
  assert "NG=F" in html
  assert "near floor CL=F +0.014" in html


def test_cme_platform_outage_recovery_status_window_active():
  from app.engines.us_stocks_open_checklist import platform_outage_recovery_status

  status = platform_outage_recovery_status(
    in_session=True,
    minutes_since_open=120,
    open_ready_symbols=["NG=F"],
    has_burst_scan=False,
    has_auto_entry=False,
    burst_events=[],
    auto_entry_events=[],
  )
  assert status["window_active"] is True
  assert status["grace_minutes_remaining"] == 150


def test_verify_cme_post_open_script_includes_outage_recovery():
  from pathlib import Path

  text = (
    Path(__file__).resolve().parents[2] / "scripts" / "verify-cme-post-open.sh"
  ).read_text(encoding="utf-8")
  assert "platform_outage_recovery" in text
  assert "check_backend_suspension" in text
  assert "deploy_{code_rev" in text
