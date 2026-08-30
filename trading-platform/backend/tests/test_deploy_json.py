#!/usr/bin/env python3
"""Unit tests for deploy_json helpers used by preflight scripts."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "scripts" / "lib" / "deploy_json.py"
sys.path.insert(0, str(LIB.parent))

from deploy_json import (  # noqa: E402
  evaluate_cme_prep_preflight,
  evaluate_intel_readiness,
  minutes_until_open,
)


def test_minutes_until_open_prefers_commodities():
  prep = {
    "commodities": {"minutes_until_open": 120},
    "next_session_events": {"cme_reopen": {"minutes_until_open": 99}},
  }
  assert minutes_until_open(prep) == 120


def test_minutes_until_open_falls_back_to_cme_reopen():
  prep = {
    "commodities": {},
    "next_session_events": {"cme_reopen": {"minutes_until_open": "540"}},
  }
  assert minutes_until_open(prep) == 540


def test_cme_prep_preflight_errors_when_minutes_missing():
  errors, _ = evaluate_cme_prep_preflight({"commodities": {}, "next_session_events": {}})
  assert "missing_minutes_until_open" in errors


def test_cme_prep_preflight_requires_auto_entry_when_symbols_queued():
  prep = {
    "commodities": {
      "minutes_until_open": 30,
      "open_ready_symbols": ["NG=F"],
      "auto_entry_queued": False,
    }
  }
  errors, _ = evaluate_cme_prep_preflight(prep)
  assert "auto_entry_not_queued" in errors


def test_intel_readiness_partial_when_sources_ok_but_snapshot_behind():
  sources = {
    "sources": [
      {"source": "x", "collection_mode": "twitter_api"},
      {"source": "tradingview", "scoring_excludes_synthetic": True},
    ]
  }
  snapshot = {"platform_revision": "2026-08-29-r336"}
  assert (
    evaluate_intel_readiness(
      sources,
      snapshot,
      prod_rev="2026-08-29-r336",
      code_rev="2026-08-29-r388",
    )
    == "partial"
  )


def test_intel_readiness_ok_when_revision_matches_and_snapshot_fields_present():
  sources = {
    "sources": [
      {"source": "x", "collection_mode": "google_news_rss"},
      {"source": "tradingview", "scoring_excludes_synthetic": True},
    ]
  }
  snapshot = {
    "platform_revision": "2026-08-29-r388",
    "x_intel_collection_mode": "google_news_rss",
    "tradingview_item_breakdown": {"webhook": 1, "synthetic": 0},
  }
  assert (
    evaluate_intel_readiness(
      sources,
      snapshot,
      prod_rev="2026-08-29-r388",
      code_rev="2026-08-29-r388",
    )
    == "ok"
  )


def test_cli_cme_prep_preflight_reads_stdin():
  payload = json.dumps(
    {
      "commodities": {
        "minutes_until_open": 10,
        "auto_entry_queued": True,
        "open_ready_symbols": ["NG=F"],
        "prep_phase": "extended",
      }
    }
  )
  proc = subprocess.run(
    [sys.executable, str(LIB), "cme-prep-preflight"],
    input=payload,
    text=True,
    capture_output=True,
    check=False,
  )
  assert proc.returncode == 0
  assert "minutes_until_open=10" in proc.stdout
