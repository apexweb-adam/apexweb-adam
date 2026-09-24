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
  evaluate_post_deploy,
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
      {"source": "political", "status": "active"},
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


def test_post_deploy_ok_when_revision_current_without_deploy_window():
  status = {
    "deploy": {
      "platform_revision": "2026-08-29-r392",
      "platform_revision_current": True,
    },
    "session_open_checklists": {"cme_reopen": {"ready": True, "phase": "preflight"}},
    "learning": {
      "trade_analyses": 1,
      "daily_reviews": 1,
      "insights_applied": 4,
      "intel_pattern_count": 1,
      "intel_pattern_alerts": ["commodities: TikTok/social hype"],
    },
    "content_study": {
      "insights_applied": 4,
      "recent": [
        {
          "source_type": "political",
          "source_label": "Political",
          "title": "Tariff headline",
          "applied": True,
        }
      ],
    },
  }
  checklist = {"open_ready": {"sticky_symbols": []}}
  snapshot = {
    "platform_revision": "2026-08-29-r392",
    "platform_revision_current": True,
    "run_deploy_window_command": "x",
    "wait_for_deploy_command": "y",
    "github_token_configured": False,
    "fomo_bearer_configured": False,
    "fomo_bearer_nudge_tier": "expired",
    "x_intel_collection_mode": "twitter_api",
    "crm_learning_verify_command": "bash trading-platform/scripts/verify-crm-learning.sh",
    "deploy_credentials_nudges": ["GITHUB_TOKEN missing on Render — deploy staleness checks incomplete"],
  }
  errors = evaluate_post_deploy(status, checklist, snapshot, expected="2026-08-29-r392")
  assert errors == []


def test_post_deploy_flags_content_study_missing_source_label():
  status = {
    "deploy": {
      "platform_revision": "2026-08-29-r468",
      "platform_revision_current": True,
    },
    "session_open_checklists": {"cme_reopen": {"ready": True, "phase": "preflight"}},
    "learning": {"trade_analyses": 1, "daily_reviews": 1},
    "content_study": {
      "insights_applied": 2,
      "recent": [{"source_type": "political", "title": "Tariff", "applied": True}],
    },
  }
  checklist = {"open_ready": {"sticky_symbols": []}}
  snapshot = {
    "platform_revision": "2026-08-29-r468",
    "platform_revision_current": True,
    "run_deploy_window_command": "x",
    "wait_for_deploy_command": "y",
    "github_token_configured": True,
    "fomo_bearer_configured": True,
    "fomo_bearer_nudge_tier": "ok",
    "x_intel_collection_mode": "twitter_api",
  }
  errors = evaluate_post_deploy(status, checklist, snapshot, expected="2026-08-29-r468")
  assert "content_study_missing_source_label" in errors


def test_intel_readiness_requires_political_source_when_revision_matches():
  sources = {
    "sources": [
      {"source": "x", "collection_mode": "google_news_rss"},
      {"source": "tradingview", "scoring_excludes_synthetic": True},
      {"source": "political", "status": "active"},
    ]
  }
  snapshot = {
    "platform_revision": "2026-08-29-r468",
    "x_intel_collection_mode": "google_news_rss",
    "tradingview_item_breakdown": {"webhook": 1, "synthetic": 0},
  }
  assert (
    evaluate_intel_readiness(
      sources,
      snapshot,
      prod_rev="2026-08-29-r468",
      code_rev="2026-08-29-r468",
    )
    == "ok"
  )


def test_post_deploy_uses_snapshot_learning_when_status_sparse():
  status = {
    "deploy": {
      "platform_revision": "2026-08-29-r468",
      "platform_revision_current": True,
    },
    "session_open_checklists": {"cme_reopen": {"ready": True, "phase": "preflight"}},
  }
  checklist = {"open_ready": {"sticky_symbols": []}}
  snapshot = {
    "platform_revision": "2026-08-29-r468",
    "platform_revision_current": True,
    "run_deploy_window_command": "x",
    "wait_for_deploy_command": "y",
    "github_token_configured": True,
    "fomo_bearer_configured": True,
    "fomo_bearer_nudge_tier": "ok",
    "x_intel_collection_mode": "twitter_api",
    "learning": {
      "trade_analyses": 3,
      "daily_reviews": 2,
      "insights_applied": 1,
      "intel_pattern_count": 0,
    },
    "content_study": {
      "insights_applied": 1,
      "recent": [
        {
          "source_type": "political",
          "source_label": "Political",
          "title": "Tariff headline",
          "applied": True,
        }
      ],
    },
  }
  errors = evaluate_post_deploy(status, checklist, snapshot, expected="2026-08-29-r468")
  assert errors == []


def test_post_deploy_check_flags_revision_mismatch():
  status = {"deploy": {"platform_revision": "2026-08-29-r336"}, "learning": {}}
  checklist = {"open_ready": {"sticky_symbols": []}}
  snapshot = {
    "platform_revision": "2026-08-29-r336",
    "cme_deploy_window": {"in_window": False},
    "run_deploy_window_command": "x",
    "wait_for_deploy_command": "y",
    "github_token_configured": True,
    "fomo_bearer_configured": True,
    "fomo_bearer_nudge_tier": "ok",
  }
  errors = evaluate_post_deploy(status, checklist, snapshot, expected="2026-08-29-r388")
  assert "revision_mismatch" in errors


def test_cli_post_deploy_check():
  import tempfile

  status = {
    "deploy": {"platform_revision": "2026-08-29-r388", "cme_deploy_window": {}},
    "session_open_checklists": {"cme_reopen": {"ready": True, "phase": "preflight"}},
    "learning": {"trade_analyses": 1},
  }
  checklist = {"open_ready": {"sticky_symbols": ["NG=F"]}}
  snapshot = {
    "platform_revision": "2026-08-29-r388",
    "cme_deploy_window": {"in_window": True},
    "run_deploy_window_command": "x",
    "wait_for_deploy_command": "y",
    "github_token_configured": True,
    "fomo_bearer_configured": True,
    "fomo_bearer_nudge_tier": "ok",
    "x_intel_collection_mode": "twitter_api",
  }
  with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as sf:
    json.dump(status, sf)
    status_path = sf.name
  with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as cf:
    json.dump(checklist, cf)
    checklist_path = cf.name
  with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as nf:
    json.dump(snapshot, nf)
    snapshot_path = nf.name
  proc = subprocess.run(
    [
      sys.executable,
      str(LIB),
      "post-deploy-check",
      "--status-file",
      status_path,
      "--checklist-file",
      checklist_path,
      "--snapshot-file",
      snapshot_path,
      "--expected",
      "2026-08-29-r388",
    ],
    capture_output=True,
    text=True,
    check=False,
  )
  assert proc.returncode == 0, proc.stdout + proc.stderr

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
