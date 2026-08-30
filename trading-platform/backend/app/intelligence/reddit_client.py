"""Shared Reddit API client with OAuth token cache and public fallback."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings

REDDIT_USER_AGENT = "ApexTradingBot/1.0 by /u/apexweb"
OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_API_BASE = "https://oauth.reddit.com"
PUBLIC_API_BASE = "https://www.reddit.com"

_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def reddit_oauth_configured() -> bool:
  return bool(settings.reddit_client_id and settings.reddit_client_secret)


def _public_reddit_url(url: str) -> str:
  parsed = urlparse(url)
  path = parsed.path or url
  if path.startswith("http"):
    return path.replace(OAUTH_API_BASE, PUBLIC_API_BASE)
  if not path.startswith("/"):
    path = f"/{path}"
  return f"{PUBLIC_API_BASE}{path}"


async def get_reddit_access_token(*, force_refresh: bool = False) -> str | None:
  if not reddit_oauth_configured():
    return None
  now = time.time()
  cached = _token_cache.get("access_token")
  if cached and not force_refresh and now < float(_token_cache.get("expires_at") or 0):
    return cached
  try:
    async with httpx.AsyncClient(timeout=10) as client:
      response = await client.post(
        OAUTH_TOKEN_URL,
        auth=(settings.reddit_client_id, settings.reddit_client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": REDDIT_USER_AGENT},
      )
      response.raise_for_status()
      payload = response.json()
      token = payload.get("access_token")
      if not token:
        return None
      expires_in = int(payload.get("expires_in") or 3600)
      _token_cache["access_token"] = token
      # Refresh 5 minutes before expiry.
      _token_cache["expires_at"] = now + max(60, expires_in - 300)
      return token
  except Exception as exc:
    print(f"Reddit OAuth error: {exc}")
    return None


async def get_reddit_headers(*, force_refresh: bool = False) -> dict[str, str]:
  headers = {"User-Agent": REDDIT_USER_AGENT}
  token = await get_reddit_access_token(force_refresh=force_refresh)
  if token:
    headers["Authorization"] = f"Bearer {token}"
  return headers


async def reddit_get_json(
  client: httpx.AsyncClient,
  url: str,
  *,
  params: dict[str, Any] | None = None,
  headers: dict[str, str] | None = None,
) -> dict[str, Any]:
  """GET Reddit JSON using OAuth when configured; fall back to public API on 401."""
  request_headers = headers or await get_reddit_headers()
  oauth_url = url
  if url.startswith(PUBLIC_API_BASE):
    oauth_url = url.replace(PUBLIC_API_BASE, OAUTH_API_BASE, 1)
  elif url.startswith("/"):
    base = OAUTH_API_BASE if request_headers.get("Authorization") else PUBLIC_API_BASE
    oauth_url = f"{base}{url}"

  response = await client.get(oauth_url, params=params, headers=request_headers)
  if response.status_code == 401 and request_headers.get("Authorization"):
    refreshed = await get_reddit_headers(force_refresh=True)
    response = await client.get(oauth_url, params=params, headers=refreshed)
  if response.status_code == 401 or not request_headers.get("Authorization"):
    public_url = _public_reddit_url(oauth_url)
    response = await client.get(
      public_url,
      params=params,
      headers={"User-Agent": REDDIT_USER_AGENT},
    )
  response.raise_for_status()
  return response.json()


def clear_reddit_token_cache() -> None:
  _token_cache["access_token"] = None
  _token_cache["expires_at"] = 0.0
