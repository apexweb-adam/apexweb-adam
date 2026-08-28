"""Tests for dashboard bundle ranking during verified preview discovery."""

from app.engines.deploy_status import bundle_rank


def test_bundle_rank_prefers_newer_revisions():
  assert bundle_rank({"bundleRevision": "2026-08-28-r25", "features": {"activeGate": True}}) == 100
  assert bundle_rank({"bundleRevision": "2026-08-28-r25", "features": {"activeGate": True}}) > bundle_rank(
    {"bundleRevision": "2026-08-28-r18", "features": {"activeGate": True}}
  )
  assert bundle_rank({"bundleRevision": "2026-08-28-r18", "features": {"activeGate": True}}) == 18
