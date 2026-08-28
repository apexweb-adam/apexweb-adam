"""GitHub third-party commit statuses can block Render checksPass auto-deploy."""

from app.engines.deploy_status import summarize_github_checks_blocker


def test_summarize_github_checks_blocker_detects_queued_integrations():
  statuses = [
    {"context": "Vercel", "state": "queued", "description": ""},
    {"context": "Netlify", "state": "queued", "description": ""},
    {"context": "GitHub Actions", "state": "success", "description": "ok"},
  ]
  result = summarize_github_checks_blocker(statuses)
  assert result["blocked"] is True
  assert result["combined_state"] == "pending"
  assert any("Vercel" in ctx for ctx in result["blocking_contexts"])
  assert any("Netlify" in ctx for ctx in result["blocking_contexts"])


def test_summarize_github_checks_blocker_clear_when_only_actions_success():
  statuses = [
    {"context": "GitHub Actions", "state": "success", "description": "ok"},
    {"context": "test", "state": "success", "description": "ok"},
  ]
  result = summarize_github_checks_blocker(statuses)
  assert result["blocked"] is False
  assert result["combined_state"] == "success"
