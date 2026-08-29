// ==UserScript==
// @name         Apex Phantom → Apex Trading Bridge
// @namespace    https://apex-trading-backend.onrender.com
// @version      1.0.0
// @description  Forward Phantom wallet portfolio snapshots to Apex intel webhook
// @match        https://phantom.app/*
// @match        https://*.phantom.app/*
// @match        https://phantom.com/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @grant        GM_xmlhttpRequest
// @connect      apex-trading-backend.onrender.com
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const STORAGE_KEY = "apex_phantom_bridge_v1";
  const DEFAULT_WEBHOOK =
    "https://apex-trading-backend.onrender.com/api/webhooks/phantom";
  const POLL_MS = 5 * 60 * 1000;

  const state = {
    webhookUrl: DEFAULT_WEBHOOK,
    secret: "",
    walletAddress: "",
    debug: false,
    lastSentAt: null,
  };

  function loadConfig() {
    try {
      const raw = GM_getValue(STORAGE_KEY, "{}");
      const cfg = typeof raw === "string" ? JSON.parse(raw) : raw;
      Object.assign(state, cfg);
    } catch (_) {}
  }

  function saveConfig() {
    GM_setValue(STORAGE_KEY, JSON.stringify(state));
  }

  function log(...args) {
    if (state.debug) console.log("[phantom-bridge]", ...args);
  }

  function postPayload(payload) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method: "POST",
        url: state.webhookUrl,
        headers: { "Content-Type": "application/json" },
        data: JSON.stringify(payload),
        onload: (res) => resolve(res),
        onerror: (err) => reject(err),
      });
    });
  }

  async function forwardPortfolio(holdings) {
    if (!state.secret) return;
    const wallet = state.walletAddress || "phantom_user";
    let portfolioUsd = 0;
    const rows = Array.isArray(holdings) ? holdings : [];
    for (const row of rows) {
      const symbol = (row.symbol || row.ticker || "").toUpperCase();
      const usd = Number(row.usd || row.valueUsd || row.balance_usd || 0);
      if (!symbol) continue;
      portfolioUsd += usd;
      try {
        await postPayload({
          secret: state.secret,
          event_type: "holdings",
          symbol,
          wallet_address: wallet,
          chain: "solana",
          balance_usd: usd,
          message: `Phantom UI holding ${symbol}`,
          url: `phantom:ui:${wallet}:${symbol}:${new Date().toISOString().slice(0, 13)}`,
        });
      } catch (e) {
        log("forward error", symbol, e);
      }
    }
    if (rows.length === 0) {
      await postPayload({
        secret: state.secret,
        event_type: "portfolio",
        symbol: "SOL",
        wallet_address: wallet,
        chain: "solana",
        balance_usd: portfolioUsd,
        message: "Phantom portfolio heartbeat",
      });
    }
    state.lastSentAt = new Date().toISOString();
    saveConfig();
  }

  async function pollFromPage() {
    // Best-effort scrape when Phantom web UI exposes token rows in DOM.
    const text = document.body ? document.body.innerText : "";
    if (!/SOL|portfolio|balance/i.test(text)) return;
    const holdings = [];
    document.querySelectorAll("[data-token-symbol], [data-symbol]").forEach((el) => {
      const symbol = (el.getAttribute("data-token-symbol") || el.getAttribute("data-symbol") || "").toUpperCase();
      if (symbol) holdings.push({ symbol, usd: 0 });
    });
    if (holdings.length) await forwardPortfolio(holdings);
  }

  GM_registerMenuCommand("Apex Phantom bridge: configure", () => {
    const secret = prompt("TradingView webhook secret:", state.secret || "");
    if (secret !== null) state.secret = secret.trim();
    const wallet = prompt("Your Solana wallet address (optional):", state.walletAddress || "");
    if (wallet !== null) state.walletAddress = wallet.trim();
    saveConfig();
    alert("Saved. Keep Phantom open for periodic portfolio forwarding.");
  });

  loadConfig();
  setInterval(pollFromPage, POLL_MS);
  setTimeout(pollFromPage, 8000);
  log("phantom bridge ready");
})();
