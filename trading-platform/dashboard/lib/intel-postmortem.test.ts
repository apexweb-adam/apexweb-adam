import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { detectIntelPostMortemSources } from "./intel-postmortem.ts";

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

  it("returns empty list when no intel keywords are present", () => {
    const sources = detectIntelPostMortemSources(
      "Market moved against position - normal variance",
      "Review if entry timing could be improved"
    );
    assert.equal(sources.length, 0);
  });
});
