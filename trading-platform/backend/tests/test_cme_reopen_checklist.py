"""Tests for CME reopen checklist builder."""

from app.engines.cme_reopen_checklist import (
  build_cme_reopen_checks,
  _symbols_below_floor,
)


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


def test_format_cme_checklist_crm_html():
  from app.engines.cme_reopen_checklist import format_cme_checklist_crm_html

  html = format_cme_checklist_crm_html(
    {
      "phase": "preflight",
      "ready": True,
      "minutes_until_open": 900,
      "open_ready": {"symbols": ["NG=F"], "composite_floor": 0.42},
      "checks": [
        {"id": "auto_entry_queued", "status": "pass", "message": "queued NG=F"},
      ],
    }
  )
  assert "CME reopen checklist" in html
  assert "auto_entry_queued" in html
  assert "NG=F" in html
