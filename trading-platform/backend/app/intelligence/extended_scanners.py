import json
from datetime import datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.intelligence.scanner import (
  IntelligenceScanner,
  analyze_sentiment,
  categorize,
  extract_symbols,
  relevance_score,
)
from app.models.entities import IntelligenceItem

YOUTUBE_CHANNELS = [
  ("UCuAXFkgsw1L7xaCfnd5YJOg", "Benjamin Cowen - Into The Cryptoverse"),
  ("UCGy7SkBjcIAgTiwkXetPn6g", "The Chart Guys"),
  ("UCqK_GSMbpiV8spgD3ZGloSw", "Coin Bureau"),
  ("UCBJycsmduvYEL83R_U4JriQ", "Andreas Antonopoulos"),
]

X_SEARCH_QUERIES = [
  "bitcoin OR btc OR crypto",
  "solana OR memecoin",
  "stock market OR nasdaq",
  "trump tariff OR fed rate",
  "gold price OR oil price",
]

POLITICAL_QUERIES = [
  "donald trump",
  "trump tariff",
  "trump crypto",
  "trump fed",
  "trump executive order market",
]

TIKTOK_GOOGLE_NEWS_QUERIES = [
  "tiktok crypto trading",
  "tiktok bitcoin",
  "tiktok stock trading",
  "tiktok memecoin",
]

POLYMARKET_KEYWORDS = [
  "bitcoin", "btc", "crypto", "ethereum", "solana", "trump", "fed",
  "tariff", "election", "gold", "oil", "recession", "rate cut",
]


class ExtendedIntelligenceScanner(IntelligenceScanner):
  """Extended scanners for X, YouTube, TikTok, Polymarket, and political signals."""

  async def scan_all(self) -> int:
    count = await super().scan_all()
    count += await self._scan_youtube()
    count += await self._scan_polymarket()
    count += await self._scan_political()
    count += await self._scan_tiktok_news()
    if settings.twitter_bearer_token:
      count += await self._scan_x_twitter()
    await self.session.commit()
    return count

  async def _add_item(
    self,
    source: str,
    title: str,
    content: str,
    url: str,
    category: str | None = None,
  ) -> bool:
    full_text = f"{title} {content}"
    existing = await self.session.execute(
      select(IntelligenceItem).where(
        (IntelligenceItem.url == url[:1000]) | (IntelligenceItem.title == title[:500])
      )
    )
    if existing.scalar_one_or_none():
      return False

    cat = category or categorize(full_text)
    self.session.add(
      IntelligenceItem(
        source=source,
        category=cat,
        title=title[:500],
        content=content[:2000],
        url=url[:1000],
        sentiment=analyze_sentiment(full_text),
        relevance_score=relevance_score(full_text, cat),
        symbols_mentioned=extract_symbols(full_text),
      )
    )
    return True

  async def _scan_youtube(self) -> int:
    count = 0
    async with httpx.AsyncClient(timeout=15) as client:
      for channel_id, channel_name in YOUTUBE_CHANNELS:
        try:
          url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
          response = await client.get(url, headers={"User-Agent": "ApexTradingBot/1.0"})
          feed = feedparser.parse(response.text)
          for entry in feed.entries[:5]:
            title = entry.get("title", "")
            content = entry.get("summary", "")
            link = entry.get("link", "")
            full_title = f"[{channel_name}] {title}"
            if await self._add_item("youtube", full_title, content, link):
              count += 1
        except Exception as e:
          print(f"YouTube scan error for {channel_name}: {e}")
    return count

  async def _scan_x_twitter(self) -> int:
    count = 0
    headers = {"Authorization": f"Bearer {settings.twitter_bearer_token}"}
    async with httpx.AsyncClient(timeout=15) as client:
      for query in X_SEARCH_QUERIES:
        try:
          response = await client.get(
            "https://api.twitter.com/2/tweets/search/recent",
            headers=headers,
            params={
              "query": f"{query} -is:retweet lang:en",
              "max_results": 10,
              "tweet.fields": "created_at,public_metrics",
            },
          )
          if response.status_code != 200:
            print(f"X API error: {response.status_code}")
            continue

          tweets = response.json().get("data", [])
          for tweet in tweets:
            text = tweet.get("text", "")
            tweet_id = tweet.get("id", "")
            url = f"https://twitter.com/i/status/{tweet_id}"
            if await self._add_item("x", text[:500], text, url):
              count += 1
        except Exception as e:
          print(f"X scan error for '{query}': {e}")
    return count

  async def _scan_polymarket(self) -> int:
    count = 0
    try:
      async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
          f"{settings.polymarket_api_url}/markets",
          params={"active": "true", "limit": 50, "order": "volume24hr", "ascending": "false"},
        )
        if response.status_code != 200:
          return 0

        markets = response.json()
        for market in markets:
          question = market.get("question", "")
          q_lower = question.lower()
          if not any(kw in q_lower for kw in POLYMARKET_KEYWORDS):
            continue

          prices = json.loads(market.get("outcomePrices", "[]"))
          yes_price = float(prices[0]) if prices else 0.5
          sentiment = (yes_price - 0.5) * 2

          volume_24h = market.get("volume24hr", 0)
          slug = market.get("slug", "")
          url = f"https://polymarket.com/event/{slug}"
          content = (
            f"Yes probability: {yes_price:.1%} | 24h volume: ${volume_24h:,.0f} | "
            f"{market.get('description', '')[:500]}"
          )

          if await self._add_item("polymarket", question, content, url, "political"):
            count += 1
    except Exception as e:
      print(f"Polymarket scan error: {e}")
    return count

  async def _scan_political(self) -> int:
    count = 0
    async with httpx.AsyncClient(timeout=15) as client:
      for query in POLITICAL_QUERIES:
        try:
          rss_url = (
            f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
            "&hl=en-US&gl=US&ceid=US:en"
          )
          response = await client.get(rss_url, headers={"User-Agent": "ApexTradingBot/1.0"})
          feed = feedparser.parse(response.text)
          for entry in feed.entries[:5]:
            title = entry.get("title", "")
            content = entry.get("summary", "")
            link = entry.get("link", "")
            if await self._add_item("political", title, content, link, "political"):
              count += 1
        except Exception as e:
          print(f"Political scan error for '{query}': {e}")

      try:
        response = await client.get(
          "https://www.reddit.com/r/politics/search.json",
          params={"q": "trump market OR trump tariff OR trump crypto", "sort": "new", "limit": 10},
          headers={"User-Agent": "ApexTradingBot/1.0"},
        )
        for post in response.json().get("data", {}).get("children", []):
          data = post.get("data", {})
          title = data.get("title", "")
          selftext = data.get("selftext", "")
          url = f"https://reddit.com{data.get('permalink', '')}"
          if await self._add_item("political", f"[Trump] {title}", selftext, url, "political"):
            count += 1
      except Exception as e:
        print(f"Political Reddit scan error: {e}")

    return count

  async def _scan_tiktok_news(self) -> int:
    """Monitor TikTok trading sentiment via Google News (TikTok has no public API)."""
    count = 0
    async with httpx.AsyncClient(timeout=15) as client:
      for query in TIKTOK_GOOGLE_NEWS_QUERIES:
        try:
          rss_url = (
            f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
            "&hl=en-US&gl=US&ceid=US:en"
          )
          response = await client.get(rss_url, headers={"User-Agent": "ApexTradingBot/1.0"})
          feed = feedparser.parse(response.text)
          for entry in feed.entries[:5]:
            title = entry.get("title", "")
            content = entry.get("summary", "")
            link = entry.get("link", "")
            if await self._add_item("tiktok", title, content, link):
              count += 1
        except Exception as e:
          print(f"TikTok news scan error for '{query}': {e}")
    return count
