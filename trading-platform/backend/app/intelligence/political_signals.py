"""Structured political event classification → asset symbols and target bots."""

from __future__ import annotations

# (keywords, event_type, asset_symbols, target_bots)
POLITICAL_EVENT_PATTERNS: list[tuple[tuple[str, ...], str, list[str], list[str]]] = [
  (("tariff", "trade war", "import duty", "sanctions trade"), "tariff", ["GC", "CL", "POLITICAL"], ["commodities", "stocks_futures"]),
  (("fed", "fomc", "interest rate", "rate cut", "rate hike", "powell"), "monetary", ["POLITICAL"], ["stocks_futures", "commodities"]),
  (("inflation", "cpi", "ppi", "cost of living"), "inflation", ["GC", "POLITICAL"], ["commodities", "stocks_futures"]),
  (("election", "ballot", "campaign", "poll"), "election", ["POLITICAL"], ["polymarket", "stocks_futures"]),
  (("trump crypto", "bitcoin executive", "crypto order"), "crypto_policy", ["BTC", "ETH", "POLITICAL"], ["crypto", "polymarket"]),
  (("iran", "israel", "gaza", "ukraine", "russia", "war", "missile", "nuclear"), "geopolitics", ["GC", "CL", "POLITICAL"], ["commodities", "polymarket"]),
  (("china taiwan", "south china sea", "beijing"), "geopolitics", ["GC", "CL", "POLITICAL"], ["commodities", "stocks_futures"]),
  (("recession", "gdp", "unemployment", "jobs report"), "macro", ["POLITICAL"], ["stocks_futures", "commodities"]),
  (("oil", "opec", "crude", "energy"), "energy", ["CL", "POLITICAL"], ["commodities"]),
  (("gold", "safe haven"), "safe_haven", ["GC", "POLITICAL"], ["commodities"]),
]


def classify_political_event(text: str) -> tuple[str, list[str], list[str]]:
  """
  Classify political headline/body into event type, affected symbols, and target bots.
  Returns (event_type, symbols, target_bots).
  """
  lower = text.lower()
  for keywords, event_type, symbols, bots in POLITICAL_EVENT_PATTERNS:
    if any(kw in lower for kw in keywords):
      return event_type, symbols, bots
  return "general", ["POLITICAL"], ["commodities", "stocks_futures", "polymarket"]


def political_category(event_type: str) -> str:
  return f"political:{event_type}"


def format_political_content(content: str, event_type: str, target_bots: list[str]) -> str:
  prefix = f"[{event_type}] Targets: {', '.join(target_bots)} | "
  combined = prefix + content
  return combined[:2000]
