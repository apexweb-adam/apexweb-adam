import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { detectIntelPostMortemSources, intelSourceBadge } from "./intel-postmortem.ts";

describe("detectIntelPostMortemSources", () => {
  it("detects political and TikTok sources from root cause text", () => {
    const sources = detectIntelPostMortemSources(
      "Political intel turned negative during commodities hold",
      "Re-check tariff headlines before holding day-trade positions"
    );
    const ids = sources.map((source) => source.id);
    assert.deepEqual(ids, ["political"]);
  });

  it("detects multiple intel sources across root cause and lessons", () => {
    const sources = detectIntelPostMortemSources(
      "TikTok viral sentiment drove entry without MACD confirmation",
      "TradingView webhooks augment local TA — wait for aligned signal score"
    );
    const ids = sources.map((source) => source.id);
    assert.deepEqual(ids, ["tiktok", "tradingview"]);
  });

  it("detects X/Twitter, Reddit, YouTube, fomo, and Polymarket hooks", () => {
    const sources = detectIntelPostMortemSources(
      "X/Twitter bearish chatter preceded loss; Reddit retail hype noted",
      "YouTube strategy content and fomo copy-trade lacked confirmation; Polymarket account hook stale"
    );
    const ids = sources.map((source) => source.id);
    assert.deepEqual(ids, ["reddit", "x", "youtube", "fomo", "polymarket"]);
  });

  it("detects news headlines from post-mortem text", () => {
    const sources = detectIntelPostMortemSources(
      "News headline influenced entry without local technical confirmation",
      "Treat news as sentiment input — wait for TA alignment"
    );
    const ids = sources.map((source) => source.id);
    assert.deepEqual(ids, ["news"]);
  });

  it("maps content-study source_type values to badges", () => {
    const news = intelSourceBadge("newsapi");
    assert.ok(news);
    assert.equal(news?.label, "News");
    const tv = intelSourceBadge("tradingview");
    assert.ok(tv);
    assert.equal(tv?.label, "TradingView");
    const whale = intelSourceBadge("wallet_tracker");
    assert.ok(whale);
    assert.equal(whale?.label, "Whale");
    const hl = intelSourceBadge("hyperliquid");
    assert.ok(hl);
    assert.equal(hl?.label, "Hyperliquid");
    assert.equal(intelSourceBadge("unknown_source"), null);
  });

  it("detects crypto wallet intel sources in post-mortem text", () => {
    const sources = detectIntelPostMortemSources(
      "DexScreener trending signal drove entry without volume confirmation",
      "Hyperliquid perp signals need TA alignment"
    );
    const ids = sources.map((source) => source.id);
    assert.deepEqual(ids, ["dexscreener", "hyperliquid"]);
  });

  it("returns empty list when no intel keywords are present", () => {
    const sources = detectIntelPostMortemSources(
      "Market moved against position - normal variance",
      "Review if entry timing could be improved"
    );
    assert.equal(sources.length, 0);
  });
});
