"""Dashboard outage grace + billing suspension helpers (source parity checks)."""

from pathlib import Path

from app.engines.session_open_log import SESSION_OPEN_PLATFORM_OUTAGE_GRACE_MINUTES

ROOT = Path(__file__).resolve().parents[2]


def test_platform_outage_grace_minutes_is_270():
  assert SESSION_OPEN_PLATFORM_OUTAGE_GRACE_MINUTES == 270


def test_backend_suspension_exports_grace_countdown():
  text = (ROOT / "dashboard/lib/backend-suspension.ts").read_text()
  assert "platformOutageGraceMinutesRemaining" in text
  assert "platform_outage_grace_minutes_remaining" in text
  assert "platformOutageGraceDeadlineUtc" in text
  assert "usCashSessionCatchupMinutesRemaining" in text
  assert "outageRecoveryBots" in text
  assert "recovery_bots" in text
  assert "verify_script" in text
  assert "verify-crypto-held.sh" in text
  assert "verify-post-outage-recovery.sh" in text
  assert "verify-cme-post-open.sh" in text
  assert "us_cash_session_catchup_minutes_remaining" in text
  assert "270 * 60 * 1000" in text
  assert "forces open-ready scan" in text


def test_deploy_unblock_documents_crypto_held_recovery():
  text = (ROOT / "DEPLOY_UNBLOCK.md").read_text()
  assert "crypto held" in text
  assert "270 minutes" in text
  assert "print-outage-status.sh" in text
