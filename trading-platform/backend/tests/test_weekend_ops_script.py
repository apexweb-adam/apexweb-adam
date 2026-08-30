"""Sanity checks for weekend ops shell script operator output."""

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def test_ops_gate_summary_script_exists():
  script = SCRIPTS / "ops-gate-summary.sh"
  text = script.read_text(encoding="utf-8")
  assert "/api/profitability" in text
  assert "/api/gate/per-bot" in text
  assert "Per-bot graduation" in text
  assert "fomo bearer" in text
  assert "intel degraded" in text


def test_wait_for_render_deploy_script_exists():
  script = SCRIPTS / "wait-for-render-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "/api/deploy/snapshot" in text
  assert "platform_revision_current" in text
  assert "--verify" in text


def test_ops_gate_summary_includes_learning_loop():
  script = SCRIPTS / "ops-gate-summary.sh"
  text = script.read_text(encoding="utf-8")
  assert "Learning loop:" in text
  assert "pending_insights" in text


def test_verify_weekend_ops_includes_gate_and_revision_hints():
  script = SCRIPTS / "verify-weekend-ops.sh"
  text = script.read_text(encoding="utf-8")
  assert "Code target:" in text
  assert "ops-gate-summary.sh" in text
  assert "Profitability gate:" not in text  # delegated to helper
  assert "github_verified" in text
  assert "deploy will advance prod expected" in text
