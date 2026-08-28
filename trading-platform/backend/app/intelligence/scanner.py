import re
from datetime import datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from textblob import TextBlob

from app.config import settings
from app.models.entities import IntelligenceItem

CRYPTO_KEYWORDS = [
  "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto", "memecoin",
  "doge", "pepe", "altcoin", "defi", "blockchain", "binance", "coinbase",
]
STOCK_KEYWORDS = [
  "stock", "market", "fed", "inflation", "earnings", "nasdaq", "s&p", "dow",
  "nvidia", "apple", "tesla", "trump", "tariff", "interest rate",
]
COMMODITY_KEYWORDS = ["gold", "silver", "oil", "crude", "forex", "eurusd", "commodity"]

NEWS_FEEDS = [
  ("news", "https://feeds.feedburner.com/CoinDesk"),
  ("news", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
  ("news", "https://feeds.reuters.com/reuters/businessNews"),
  ("reddit", "https://www.reddit.com/r/cryptocurrency/.rss"),
  ("reddit", "https://www.reddit.com/r/wallstreetbets/.rss"),
  ("reddit", "https://www.reddit.com/r/CryptoMarkets/.rss"),
  ("reddit", "https://www.reddit.com/r/StockMarket/.rss"),
]


def analyze_sentiment(text: str) -> float:
  try:
    return TextBlob(text).sentiment.polarity
  except Exception:
    return 0.0


def extract_symbols(text: str) -> str:
  text_lower = text.lower()
  found: list[str] = []
  symbol_map = {
    "bitcoin": "BTC", "btc": "BTC", "ethereum": "ETH", "eth": "ETH",
    "solana": "SOL", "sol": "SOL", "doge": "DOGE", "pepe": "PEPE",
    "nvidia": "NVDA", "apple": "AAPL", "tesla": "TSLA", "gold": "GC",
    "silver": "SI", "oil": "CL", "trump": "POLITICAL",
  }
  for keyword, symbol in symbol_map.items():
    if keyword in text_lower and symbol not in found:
      found.append(symbol)
  return ",".join(found)


def categorize(text: str) -> str:
  text_lower = text.lower()
  if any(k in text_lower for k in CRYPTO_KEYWORDS):
    return "crypto"
  if any(k in text_lower for k in COMMODITY_KEYWORDS):
    return "commodities"
  if any(k in text_lower for k in STOCK_KEYWORDS):
    return "stocks"
  return "general"


def relevance_score(text: str, category: str) -> float:
  text_lower = text.lower()
  keywords = {
    "crypto": CRYPTO_KEYWORDS,
    "stocks": STOCK_KEYWORDS,
    "commodities": COMMODITY_KEYWORDS,
  }.get(category, CRYPTO_KEYWORDS + STOCK_KEYWORDS)
  matches = sum(1 for k in keywords if k in text_lower)
  return min(1.0, matches / 5)


class IntelligenceScanner:
  def __init__(self, session: AsyncSession):
    self.session = session

  async def scan_all(self) -> int:
    count = 0
    count += await self._scan_rss_feeds()
    count += await self._scan_reddit_api()
    if settings.newsapi_key:
      count += await self._scan_newsapi()
    await self.session.commit()
    return count

  async def _scan_rss_feeds(self) -> int:
    count = 0
    async with httpx.AsyncClient(timeout=15) as client:
      for source, url in NEWS_FEEDS:
        try:
          response = await client.get(url, headers={"User-Agent": "ApexTradingBot/1.0"})
          feed = feedparser.parse(response.text)
          for entry in feed.entries[:10]:
            title = entry.get("title", "")
            content = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            full_text = f"{title} {content}"

            existing = await self.session.execute(
              select(IntelligenceItem).where(IntelligenceItem.title == title[:500])
            )
            if existing.scalar_one_or_none():
              continue

            item = IntelligenceItem(
              source=source,
              category=categorize(full_text),
              title=title[:500],
              content=content[:2000],
              url=link[:1000],
              sentiment=analyze_sentiment(full_text),
              relevance_score=relevance_score(full_text, categorize(full_text)),
              symbols_mentioned=extract_symbols(full_text),
            )
            self.session.add(item)
            count += 1
        except Exception as e:
          print(f"RSS scan error for {url}: {e}")
    return count

  async def _reddit_headers(self) -> dict[str, str]:
    headers = {"User-Agent": "ApexTradingBot/1.0 by /u/apexweb"}
    if settings.reddit_client_id and settings.reddit_client_secret:
      try:
        async with httpx.AsyncClient(timeout=10) as client:
          token_resp = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            data={"grant_type": "client_credentials"},
            headers=headers,
          )
          token = token_resp.json().get("access_token")
          if token:
            headers["Authorization"] = f"Bearer {token}"
      except Exception as e:
        print(f"Reddit OAuth error: {e}")
    return headers

  async def _scan_reddit_api(self) -> int:
    count = 0
    subreddits = ["cryptocurrency", "wallstreetbets", "CryptoMarkets", "StockMarket", "politics"]
    headers = await self._reddit_headers()
    async with httpx.AsyncClient(timeout=15) as client:
      for sub in subreddits:
        for listing in ("hot", "new"):
          try:
            response = await client.get(
              f"https://oauth.reddit.com/r/{sub}/{listing}.json?limit=8",
              headers=headers,
            )
            if response.status_code == 401:
              response = await client.get(
                f"https://www.reddit.com/r/{sub}/{listing}.json?limit=8",
                headers={"User-Agent": headers["User-Agent"]},
              )
            data = response.json()
            for post in data.get("data", {}).get("children", []):
              post_data = post.get("data", {})
              title = post_data.get("title", "")
              selftext = post_data.get("selftext", "")
              url = f"https://reddit.com{post_data.get('permalink', '')}"
              full_text = f"{title} {selftext}"

              existing = await self.session.execute(
                select(IntelligenceItem).where(IntelligenceItem.url == url[:1000])
              )
              if existing.scalar_one_or_none():
                continue

              item = IntelligenceItem(
                source="reddit",
                category=categorize(full_text),
                title=title[:500],
                content=selftext[:2000],
                url=url[:1000],
                sentiment=analyze_sentiment(full_text),
                relevance_score=relevance_score(full_text, categorize(full_text)),
                symbols_mentioned=extract_symbols(full_text),
              )
              self.session.add(item)
              count += 1
          except Exception as e:
            print(f"Reddit scan error for r/{sub}/{listing}: {e}")
    return count

  async def _scan_newsapi(self) -> int:
    count = 0
    queries = ["cryptocurrency OR bitcoin", "stock market OR fed", "gold OR oil OR forex"]
    async with httpx.AsyncClient(timeout=15) as client:
      for query in queries:
        try:
          response = await client.get(
            "https://newsapi.org/v2/everything",
            params={
              "q": query,
              "sortBy": "publishedAt",
              "pageSize": 10,
              "apiKey": settings.newsapi_key,
            },
          )
          articles = response.json().get("articles", [])
          for article in articles:
            title = article.get("title", "")
            content = article.get("description", "")
            url = article.get("url", "")
            full_text = f"{title} {content}"

            existing = await self.session.execute(
              select(IntelligenceItem).where(IntelligenceItem.url == url[:1000])
            )
            if existing.scalar_one_or_none():
              continue

            item = IntelligenceItem(
              source="newsapi",
              category=categorize(full_text),
              title=title[:500],
              content=content[:2000],
              url=url[:1000],
              sentiment=analyze_sentiment(full_text),
              relevance_score=relevance_score(full_text, categorize(full_text)),
              symbols_mentioned=extract_symbols(full_text),
            )
            self.session.add(item)
            count += 1
        except Exception as e:
          print(f"NewsAPI scan error: {e}")
    return count
