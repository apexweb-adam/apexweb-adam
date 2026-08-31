"""Tests for shared Reddit OAuth client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.intelligence import reddit_client


@pytest.fixture(autouse=True)
def _clear_token_cache():
  reddit_client.clear_reddit_token_cache()
  yield
  reddit_client.clear_reddit_token_cache()


@pytest.mark.asyncio
async def test_get_reddit_access_token_caches_until_expiry():
  with patch("app.intelligence.reddit_client.settings") as mock_settings:
    mock_settings.reddit_client_id = "id"
    mock_settings.reddit_client_secret = "secret"
    with patch("httpx.AsyncClient") as mock_client_cls:
      mock_client = AsyncMock()
      mock_client.__aenter__.return_value = mock_client
      mock_client.__aexit__.return_value = None
      mock_response = MagicMock()
      mock_response.json.return_value = {"access_token": "tok123", "expires_in": 3600}
      mock_response.raise_for_status = MagicMock()
      mock_client.post = AsyncMock(return_value=mock_response)
      mock_client_cls.return_value = mock_client

      first = await reddit_client.get_reddit_access_token()
      second = await reddit_client.get_reddit_access_token()

  assert first == "tok123"
  assert second == "tok123"
  assert mock_client.post.await_count == 1


@pytest.mark.asyncio
async def test_get_reddit_headers_without_oauth():
  with patch("app.intelligence.reddit_client.settings") as mock_settings:
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    headers = await reddit_client.get_reddit_headers()
  assert headers["User-Agent"] == reddit_client.REDDIT_USER_AGENT
  assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_reddit_get_json_falls_back_to_public_on_401():
  oauth_resp = httpx.Response(401, request=httpx.Request("GET", "https://oauth.reddit.com/r/test.json"))
  public_resp = httpx.Response(
    200,
    json={"data": {"children": []}},
    request=httpx.Request("GET", "https://www.reddit.com/r/test.json"),
  )

  with patch("app.intelligence.reddit_client.settings") as mock_settings:
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    async with httpx.AsyncClient() as client:
      with patch.object(client, "get", AsyncMock(side_effect=[oauth_resp, public_resp])) as mock_get:
        data = await reddit_client.reddit_get_json(
          client,
          "https://oauth.reddit.com/r/test.json",
          headers={"User-Agent": reddit_client.REDDIT_USER_AGENT},
        )

  assert data == {"data": {"children": []}}
  assert mock_get.await_count == 2
  assert "www.reddit.com" in str(mock_get.await_args_list[-1].args[0])


def test_reddit_intel_configured_without_oauth():
  with patch("app.intelligence.reddit_client.settings") as mock_settings:
    mock_settings.reddit_client_id = ""
    mock_settings.reddit_client_secret = ""
    assert reddit_client.reddit_intel_configured(reddit_item_count=0) is True
