"""Deploy staleness must not report current when GitHub compare shows commits ahead."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.engines import deploy_status


def _clear_deploy_cache() -> None:
  deploy_status._deploy_status_cache = None
  deploy_status._deploy_status_cached_at = 0.0


def test_build_deploy_status_stale_when_compare_ahead():
  _clear_deploy_cache()
  compare = {
    "ahead_by": 3,
    "head_sha": "a1bf65d9a8f20ae1410b380c15c59b93f44f7785",
    "commits": [{"sha": "abc123", "message": "fix deploy"}],
  }

  with patch.object(deploy_status, "deployed_git_commit", return_value="e7e76a42e8ce72a40f8e9c742be9b138275e7f68"):
    with patch.object(deploy_status, "fetch_latest_main_commit", AsyncMock(return_value=None)):
      with patch.object(deploy_status, "fetch_main_sha_via_ref", AsyncMock(return_value=None)):
        with patch.object(deploy_status, "fetch_compare_to_main", AsyncMock(return_value=compare)):
          with patch.object(deploy_status, "fetch_commits_since", AsyncMock(return_value=[])):
            with patch.object(deploy_status, "fetch_vercel_dashboard_bundle", AsyncMock(return_value={})):
              result = asyncio.run(deploy_status.build_deploy_status())

  assert result["is_stale"] is True
  assert result["commits_behind"] == 1
  assert result["github_verified"] is True


def test_build_deploy_status_stale_when_github_unavailable():
  _clear_deploy_cache()
  with patch.object(deploy_status, "deployed_git_commit", return_value="e7e76a42e8ce72a40f8e9c742be9b138275e7f68"):
    with patch.object(deploy_status, "fetch_latest_main_commit", AsyncMock(return_value=None)):
      with patch.object(deploy_status, "fetch_main_sha_via_ref", AsyncMock(return_value=None)):
        with patch.object(deploy_status, "fetch_compare_to_main", AsyncMock(return_value=None)):
          with patch.object(deploy_status, "fetch_vercel_dashboard_bundle", AsyncMock(return_value={})):
            result = asyncio.run(deploy_status.build_deploy_status())

  assert result["is_stale"] is True
  assert result["github_verified"] is False
  assert result["commits_behind"] == 1
