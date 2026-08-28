import json
from datetime import datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engines.polymarket_data import is_macro_relevant_market
from app.intelligence.political_signals import (
  classify_political_event,
  format_political_content,
  political_category,
)
from app.intelligence.scanner import (
  CRYPTO_KEYWORDS,
  COMMODITY_KEYWORDS,
  IntelligenceScanner,
  STOCK_KEYWORDS,
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
  "solana OR memecoin OR pepe OR bonk OR wif",
  "pump.fun OR sol memecoin OR degen",
  "hyperliquid OR HL perp OR perps",
  "stock market OR nasdaq OR sp500",
  "trump tariff OR fed rate OR inflation",
  "gold price OR oil price OR commodities",
  "iran OR geopolitics OR war market",
  "esports OR sports betting OR nfl",
  "ai OR tech stocks OR nvidia",
  "economy OR recession OR gdp",
  "polymarket OR prediction market",
]

POLITICAL_QUERIES = [
  "donald trump",
  "trump tariff",
  "trump crypto",
  "trump fed",
  "iran nuclear",
  "israel gaza",
  "ukraine russia",
  "china taiwan",
  "fed interest rate",
  "election 2026",
  "weather forecast economy",
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

_TRADING_KEYWORDS = set(CRYPTO_KEYWORDS + STOCK_KEYWORDS + COMMODITY_KEYWORDS + POLYMARKET_KEYWORDS)


def _is_trading_relevant(text: str) -> bool:
  text_lower = text.lower()
  return any(k in text_lower for k in _TRADING_KEYWORDS)


class ExtendedIntelligenceScanner(IntelligenceScanner):
  """Extended scanners for X, YouTube, TikTok, Polymarket, and political signals."""

  async def scan_all(self) -> int:
    count = await super().scan_all()
    count += await self._scan_youtube()
    count += await self._scan_polymarket()
    if settings.polymarket_wallet_address or settings.polymarket_deposit_address:
      count += await self._scan_polymarket_account()
    count += await self._scan_political()
    count += await self._scan_tiktok_news()
    if settings.twitter_bearer_token:
      count += await self._scan_x_twitter()
    elif settings.newsapi_key:
      count += await self._scan_x_social_news_fallback()
    from app.intelligence.wallet_tracker import scan_wallet_tracker
    from app.intelligence.solana_wallet_tracker import scan_solana_wallets
    from app.intelligence.memecoin_scanner import scan_memecoin_intel

    count += await scan_wallet_tracker(self.session)
    count += await scan_solana_wallets(self.session)
    count += await scan_memecoin_intel(self.session)
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

  async def _add_political_item(self, title: str, content: str, url: str) -> bool:
    full_text = f"{title} {content}"
    existing = await self.session.execute(
      select(IntelligenceItem).where(
        (IntelligenceItem.url == url[:1000]) | (IntelligenceItem.title == title[:500])
      )
    )
    if existing.scalar_one_or_none():
      return False

    event_type, asset_symbols, target_bots = classify_political_event(full_text)
    cat = political_category(event_type)
    enriched_content = format_political_content(content, event_type, target_bots)
    symbols = extract_symbols(full_text)
    symbol_set = set(symbols.split(",")) if symbols else set()
    symbol_set.update(asset_symbols)
    symbols_combined = ",".join(sorted(s for s in symbol_set if s))

    self.session.add(
      IntelligenceItem(
        source="political",
        category=cat,
        title=title[:500],
        content=enriched_content,
        url=url[:1000],
        sentiment=analyze_sentiment(full_text),
        relevance_score=relevance_score(full_text, "political"),
        symbols_mentioned=symbols_combined[:200],
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

  async def _scan_x_social_news_fallback(self) -> int:
    """Social-style intel via NewsAPI when X tweet API is unavailable."""
    if not settings.newsapi_key:
      return 0
    count = 0
    async with httpx.AsyncClient(timeout=15) as client:
      for query in X_SEARCH_QUERIES[:6]:
        try:
          response = await client.get(
            "https://newsapi.org/v2/everything",
            params={
              "q": f"({query}) AND (twitter OR tweet OR x.com OR social media)",
              "language": "en",
              "sortBy": "publishedAt",
              "pageSize": 5,
              "apiKey": settings.newsapi_key,
            },
          )
          if response.status_code != 200:
            continue
          for article in response.json().get("articles", []):
            title = article.get("title") or ""
            if not title:
              continue
            content = article.get("description") or title
            url = article.get("url") or ""
            full_text = f"{title} {content}"
            cat = categorize(full_text)
            score = relevance_score(full_text, cat)
            if score < 0.2 and not _is_trading_relevant(full_text):
              continue
            if await self._add_item("x", f"[social-news] {title}", content, url):
              count += 1
        except Exception as e:
          print(f"X news fallback error for '{query}': {e}")
    return count

  async def _scan_x_twitter(self) -> int:
    count = 0
    api_blocked = False
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
          if response.status_code in (402, 403):
            api_blocked = True
            print(f"X API error: {response.status_code}")
            continue
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

    if count == 0 and (api_blocked or settings.twitter_bearer_token):
      print("[X] Using NewsAPI social fallback for X intel slot")
      count += await self._scan_x_social_news_fallback()
    return count

  async def _scan_polymarket(self) -> int:
    count = 0
    try:
      async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
          f"{settings.polymarket_api_url}/markets",
          params={"active": "true", "limit": 60, "order": "volume24hr", "ascending": "false"},
        )
        if response.status_code != 200:
          return 0

        for market in response.json():
          if not is_macro_relevant_market(market):
            continue
          question = market.get("question", "")
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

  async def _scan_polymarket_account(self) -> int:
    """Fetch user's Polymarket positions via public Data API (+ optional CLOB key)."""
    count = 0
    wallets = [
      w.strip()
      for w in [settings.polymarket_wallet_address, settings.polymarket_deposit_address]
      if w and w.strip()
    ]
    if not wallets:
      return 0

    headers: dict[str, str] = {}
    if settings.polymarket_api_key:
      headers["POLY_API_KEY"] = settings.polymarket_api_key

    try:
      async with httpx.AsyncClient(timeout=15) as client:
        for wallet in wallets:
          response = await client.get(
            f"{settings.polymarket_data_api_url}/positions",
            params={"user": wallet, "limit": 25, "sortBy": "CASHPNL", "sortDirection": "DESC"},
            headers=headers,
          )
          if response.status_code != 200:
            print(f"Polymarket account API error for {wallet[:10]}…: {response.status_code}")
            continue

          positions = response.json()
          if not positions:
            profile = settings.polymarket_profile_url or f"https://polymarket.com/profile/{wallet}"
            title = f"[Your Polymarket] Account linked ({wallet[:6]}…{wallet[-4:]})"
            content = "No open positions. Wallet connected for prediction-market signal overlay."
            if await self._add_item("polymarket_account", title, content, profile, "political"):
              count += 1
            continue

          for pos in positions:
            title = pos.get("title", "Unknown market")
            outcome = pos.get("outcome", "")
            size = pos.get("size", 0)
            cur_price = pos.get("curPrice", 0)
            cash_pnl = pos.get("cashPnl", 0)
            slug = pos.get("slug", pos.get("eventSlug", ""))
            url = f"https://polymarket.com/event/{slug}" if slug else f"https://polymarket.com/profile/{wallet}"

            content = (
              f"Your position: {outcome} | Size: {size:.2f} | Price: {cur_price:.2f} | "
              f"PnL: ${cash_pnl:,.2f}"
            )
            sentiment = 0.3 if cash_pnl > 0 else -0.3 if cash_pnl < 0 else 0.0

            full_text = f"{title} {content}"
            existing = await self.session.execute(
              select(IntelligenceItem).where(
                IntelligenceItem.source == "polymarket_account",
                IntelligenceItem.title == f"[Your Position] {title[:450]}",
              )
            )
            if existing.scalar_one_or_none():
              continue

            self.session.add(
              IntelligenceItem(
                source="polymarket_account",
                category="political",
                title=f"[Your Position] {title[:450]}",
                content=content[:2000],
                url=url[:1000],
                sentiment=sentiment,
                relevance_score=relevance_score(full_text, "political"),
                symbols_mentioned=extract_symbols(full_text),
              )
            )
            count += 1
    except Exception as e:
      print(f"Polymarket account scan error: {e}")
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
            if await self._add_political_item(title, content, link):
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
          if await self._add_political_item(f"[Trump] {title}", selftext, url):
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
            full_text = f"{title} {content}"
            cat = categorize(full_text)
            score = relevance_score(full_text, cat)
            if score < 0.2 and not _is_trading_relevant(full_text):
              continue
            if await self._add_item("tiktok", title, content, link):
              count += 1
        except Exception as e:
          print(f"TikTok news scan error for '{query}': {e}")
    return count
