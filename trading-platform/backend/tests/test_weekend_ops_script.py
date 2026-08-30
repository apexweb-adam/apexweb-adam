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


def test_wait_for_render_deploy_prints_snapshot_integrations():
  script = SCRIPTS / "wait-for-render-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "snapshot integrations" in text
  assert "fomo_bearer_configured" in text


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
  assert "r367-r371" in text
  assert "check-deploy-credentials.sh" in text
  assert "fomo_bearer_configured" in text


def test_verify_pre_deploy_saves_crm_baseline():
  script = SCRIPTS / "verify-pre-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert ".crm-load-baseline" in text
  assert "CRM landing baseline" in text
  assert "check-deploy-credentials.sh" in text


def test_check_fomo_bearer_script_exists():
  script = SCRIPTS / "check-fomo-bearer.sh"
  text = script.read_text(encoding="utf-8")
  assert "/api/deploy/snapshot" in text
  assert "/api/status" in text
  assert "fomo bearer status unknown" in text or "fomo bearer expired" in text
  assert "fomo-set-bearer.sh" in text


def test_check_deploy_credentials_supports_strict_mode():
  script = SCRIPTS / "check-deploy-credentials.sh"
  text = script.read_text(encoding="utf-8")
  assert "--strict" in text
  assert "STRICT_FLAG" in text


def test_run_deploy_window_strict_credentials_on_live_deploy():
  script = SCRIPTS / "run-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "Checking deploy credentials (strict)" in text
  assert "check-deploy-credentials.sh --strict" in text
  assert "Deploy aborted" in text


def test_run_deploy_window_includes_credentials_check():
  script = SCRIPTS / "run-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "check-deploy-credentials.sh" in text
  assert "print-deploy-window-summary.sh" in text


def test_print_deploy_window_summary_script_exists():
  script = SCRIPTS / "print-deploy-window-summary.sh"
  text = script.read_text(encoding="utf-8")
  assert "Deploy Window Operator Summary" in text
  assert "/api/deploy/snapshot" in text
  assert "cme-reopen-checklist" in text
  assert "deploy_credentials_ready" in text
  assert "fomo_bearer_nudge" in text
  assert "x_intel_collection_mode" in text
  assert "deploy_json.py" in text
  assert "Intel: sources API ready" in text
  assert "verify-cme-post-open.sh" in text


def test_run_deploy_window_includes_summary_script():
  script = SCRIPTS / "run-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "print-deploy-window-summary.sh" in text
  assert "try-promote-vercel-dashboard.sh" in text


def test_try_promote_vercel_dashboard_script_exists():
  script = SCRIPTS / "try-promote-vercel-dashboard.sh"
  text = script.read_text(encoding="utf-8")
  assert "VERCEL_TOKEN" in text
  assert "promote-vercel-dashboard.sh" in text
  assert "/api/dashboard-url" in text


def test_check_deploy_credentials_includes_fomo_nudge():
  script = SCRIPTS / "check-deploy-credentials.sh"
  text = script.read_text(encoding="utf-8")
  assert "fomo_bearer_nudge_message" in text


def test_check_deploy_credentials_script_exists():
  script = SCRIPTS / "check-deploy-credentials.sh"
  text = script.read_text(encoding="utf-8")
  assert "/api/deploy/snapshot" in text
  assert "deploy_credentials_ready" in text
  assert "ACTION REQUIRED before deploy" in text
  assert "check-fomo-bearer.sh" in text
  assert "check-github-token.sh" in text


def test_verify_weekend_ops_includes_gate_and_revision_hints():
  script = SCRIPTS / "verify-weekend-ops.sh"
  text = script.read_text(encoding="utf-8")
  assert "Code target:" in text
  assert "ops-gate-summary.sh" in text
  assert "Profitability gate:" not in text  # delegated to helper
  assert "deploy_credentials_ready" in text
  assert "deploy_credentials_warnings" in text
  assert "print-deploy-window-summary.sh" in text
  assert "deploy will advance prod expected" in text


def test_check_github_token_script_exists():
  script = SCRIPTS / "check-github-token.sh"
  text = script.read_text(encoding="utf-8")
  assert "/api/deploy/snapshot" in text
  assert "GITHUB_TOKEN" in text
  assert "sync-render-env.sh" in text


def test_watch_deploy_window_auto_deploy_uses_run_deploy_window():
  script = SCRIPTS / "watch-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  marker = "Auto-deploy enabled — running full deploy window workflow"
  assert marker in text
  block = text.split(marker, 1)[0]
  assert "check-deploy-credentials.sh --strict" in block
  block = text.split(marker, 1)[1]
  assert 'bash "$ROOT/scripts/run-deploy-window.sh"' in block
  assert "sync-render-env.sh" not in block
  assert "if ! bash" in block


def test_watch_deploy_window_shows_credentials_when_active():
  script = SCRIPTS / "watch-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "deploy_credentials_ready" in text
  assert "fomo_bearer_nudge_message" in text
  assert "check-deploy-credentials.sh --strict" in text


def test_check_deploy_credentials_shows_revision_gap():
  script = SCRIPTS / "check-deploy-credentials.sh"
  text = script.read_text(encoding="utf-8")
  assert "code_target=" in text
  assert "PLATFORM_REVISION" in text
  assert "x_intel_collection_mode" in text or "google_news_rss activates" in text


def test_verify_pre_deploy_intel_readiness():
  script = SCRIPTS / "verify-pre-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "Intel source health fields" in text
  assert "r385" in text
  assert "/api/intelligence/sources" in text
  assert "deploy_json.py" in text
  assert "Intel sources API ready" in text


def test_verify_cme_reopen_uses_deploy_json_fallback():
  script = SCRIPTS / "verify-cme-reopen.sh"
  text = script.read_text(encoding="utf-8")
  assert "deploy_json.py" in text
  assert "json.load(sys.stdin)" in text
  assert "STATUS_JSON" in text


def test_deploy_json_lib_exists():
  lib = SCRIPTS / "lib" / "deploy_json.py"
  text = lib.read_text(encoding="utf-8")
  assert "intel-readiness" in text
  assert "cme-prep-preflight" in text


def test_verify_post_deploy_checks_learning_endpoint():
  script = SCRIPTS / "verify-post-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "learning/apply-pending-insights" in text
  assert "openapi.json" in text
  assert "x_intel_collection_mode" in text
  assert "scoring_excludes_synthetic" in text
  assert "/api/intelligence/sources" in text


def test_watch_deploy_window_shows_x_intel_mode():
  script = SCRIPTS / "watch-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "x_intel_collection_mode" in text


def test_verify_platform_prints_intel_health_fields():
  script = SCRIPTS / "verify-platform.sh"
  text = script.read_text(encoding="utf-8")
  assert "scoring_excludes_synthetic" in text
  assert "x_intel=" in text
