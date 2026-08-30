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
  assert "fetch_json.sh" in text


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
  assert "fetch_json.sh" in text
  assert "json.load(sys.stdin)" in text


def test_fetch_json_lib_exists():
  lib = SCRIPTS / "lib" / "fetch_json.sh"
  text = lib.read_text(encoding="utf-8")
  assert "fetch_json()" in text
  assert "attempts" in text


def test_verify_post_deploy_includes_crm_and_learning_checks():
  script = SCRIPTS / "verify-post-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "ops-gate-summary.sh" in text
  assert "/crm" in text
  assert "post-deploy-check" in text
  assert "apply-pending-insights" in text
  assert "deploy_json.py" in text
  assert ".crm-load-baseline" in text
  assert "r367-r371" in text
  assert "check-deploy-credentials.sh" in text
  assert "verify-platform.sh" in text


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


def test_scheduler_registers_open_ready_watch_job():
  script = SCRIPTS.parent / "backend" / "app" / "workers" / "scheduler.py"
  text = script.read_text(encoding="utf-8")
  assert "commodities_open_ready_watch_job" in text
  assert "commodities_open_ready_watch" in text


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
  assert "verify-cme-post-open.sh --watch" in text
  assert "sticky_symbols" in text
  assert "extended_watch dropped" in text
  assert "near_floor" in text
  assert "open_ready" in text and "blockers=" in text
  assert "prep-status" in text
  assert "CME prep watch:" in text
  assert "queue dropped" in text
  assert "us-stocks-open-checklist" in text


def test_verify_us_stocks_post_open_supports_watch_mode():
  script = SCRIPTS / "verify-us-stocks-post-open.sh"
  text = script.read_text(encoding="utf-8")
  assert "--watch" in text
  assert "Watching for US stocks post-open" in text
  assert "run_verification" in text


def test_verify_cme_post_open_supports_watch_mode():
  script = SCRIPTS / "verify-cme-post-open.sh"
  text = script.read_text(encoding="utf-8")
  assert "--watch" in text
  assert "Watching for CME post-open" in text
  assert "run_verification" in text
  assert "extended_watch" in text
  assert "expected_platform_revision" in text


def test_wait_for_render_deploy_waits_for_status_revision():
  script = SCRIPTS / "wait-for-render-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "wait_for_status_revision" in text
  assert "/api/status" in text
  assert "status-sync" in text


def test_watch_deploy_window_shows_cme_prep_when_current():
  script = SCRIPTS / "watch-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "print_cme_prep" in text
  assert "cme-reopen-checklist" in text
  assert "cme_open_in=" in text


def test_run_deploy_window_includes_summary_script():
  script = SCRIPTS / "run-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "print-deploy-window-summary.sh" in text
  assert "try-promote-vercel-dashboard.sh" in text
  assert "verify-platform.sh" in text
  assert "RUN_PLATFORM_VERIFY" in text


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


def test_check_deploy_credentials_treats_github_as_nudge():
  script = SCRIPTS / "check-deploy-credentials.sh"
  text = script.read_text(encoding="utf-8")
  assert "deploy_credentials_nudges" in text
  assert "non-blocking" in text
  assert "GITHUB_TOKEN is advisory" in text or "Normalize pre-r390" in text


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
  assert "composite_floor_ok_with_sticky_margin" in text
  assert "queue_dropped" in text
  assert "queue_dropped_in_prep_window" in text
  assert "extended_watch=" in text
  assert "CME_WATCH" in text


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
  assert "deploy_json.py" in text
  assert "post-deploy-check" in text
  assert "fetch_json.sh" in text
  assert "scoring_excludes_synthetic" in text or "intel-readiness" in text
  assert "/api/intelligence/sources" in text


def test_watch_deploy_window_shows_x_intel_mode():
  script = SCRIPTS / "watch-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "x_intel_collection_mode" in text


def test_watch_deploy_window_uses_fetch_json():
  script = SCRIPTS / "watch-deploy-window.sh"
  text = script.read_text(encoding="utf-8")
  assert "fetch_json.sh" in text
  assert "SNAPSHOT_JSON" in text
  assert "'''$SNAPSHOT'''" not in text


def test_verify_platform_prints_intel_health_fields():
  script = SCRIPTS / "verify-platform.sh"
  text = script.read_text(encoding="utf-8")
  assert "scoring_excludes_synthetic" in text
  assert "x_intel=" in text
  assert "Content study insights" in text
  assert "insights_applied" in text
  assert "deploy_credentials_ready" in text
  assert "check-deploy-credentials.sh" in text


def test_verify_pre_deploy_us_stocks_uses_fetch_json():
  script = SCRIPTS / "verify-pre-deploy.sh"
  text = script.read_text(encoding="utf-8")
  assert "us-stocks-open-checklist" in text
  assert "fetch_json" in text
  assert "'''$US_CHECKLIST'''" not in text


def test_session_open_scripts_use_fetch_json_not_heredoc():
  for name in (
    "verify-cme-post-open.sh",
    "verify-us-stocks-open.sh",
    "verify-us-stocks-post-open.sh",
  ):
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "fetch_json.sh" in text
    assert "'''$CHECKLIST'''" not in text
    assert "'''$STATUS'''" not in text
