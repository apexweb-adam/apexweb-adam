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


def test_run_deploy_window_script_exists():
  script = SCRIPTS / "run-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "verify-pre-deploy.sh" in text
  assert "wait-for-render-deploy.sh" in text
  assert "sync-render-env.sh" in text
  assert "--dry-run" in text


def test_verify_platform_uses_ops_gate_summary():
  script = SCRIPTS / "verify-platform.sh"
  text = script.read_text(encoding="utf-8")
  assert "ops-gate-summary.sh" in text
  assert "EXPECTED_DASHBOARD_BUNDLE" in text
  assert "verify-dashboard-bundle.sh" in text


def test_verify_post_deploy_includes_crm_and_learning_checks():
  script = SCRIPTS / "verify-post-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "ops-gate-summary.sh" in text
  assert "/crm" in text
  assert "learning_loop" in text
  assert "run_deploy_window_command" in text
  assert ".crm-load-baseline" in text
  assert "r367-r369" in text


def test_verify_pre_deploy_saves_crm_baseline():
  script = SCRIPTS / "verify-pre-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert ".crm-load-baseline" in text
  assert "CRM landing baseline" in text


def test_verify_weekend_ops_includes_gate_and_revision_hints():
  script = SCRIPTS / "verify-weekend-ops.sh"
  text = script.read_text(encoding="utf-8")
  assert "Code target:" in text
  assert "ops-gate-summary.sh" in text
  assert "Profitability gate:" not in text  # delegated to helper
  assert "github_verified" in text
  assert "deploy will advance prod expected" in text
