// ==UserScript==
// @name         Apex axiom.trade → Apex Trading Bridge
// @namespace    https://apex-trading-backend.onrender.com
// @version      1.0.0
// @description  Forward axiom.trade wallet trades and alerts to Apex memecoin intel webhook
// @match        https://axiom.trade/*
// @match        https://*.axiom.trade/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @run-at       document-start
// ==/UserScript==

(function () {
  "use strict";

  const STORAGE_KEY = "apex_axiom_bridge_v1";
  const DEFAULT_WEBHOOK =
    "https://apex-trading-backend.onrender.com/api/webhooks/axiom";
  const SESSION_SYNC_URL =
    "https://apex-trading-backend.onrender.com/api/admin/set-axiom-session";

  const state = {
    webhookUrl: DEFAULT_WEBHOOK,
    secret: "",
    minUsd: 100,
    debug: false,
    sessionToken: "",
    seen: new Set(),
    sent: 0,
    errors: 0,
  };

  function loadConfig() {
    try {
      const raw = GM_getValue(STORAGE_KEY, "{}");
      const cfg = typeof raw === "string" ? JSON.parse(raw) : raw;
      Object.assign(state, cfg);
      if (!Array.isArray(state.seen)) state.seen = [];
      state.seen = new Set(state.seen.slice(-400));
    } catch (_) {
      state.seen = new Set();
    }
  }

  function saveConfig() {
    GM_setValue(
      STORAGE_KEY,
      JSON.stringify({
        webhookUrl: state.webhookUrl,
        secret: state.secret,
        minUsd: state.minUsd,
        debug: state.debug,
        seen: Array.from(state.seen).slice(-400),
      })
    );
  }

  function log(...args) {
    if (state.debug) console.log("[axiom-bridge]", ...args);
  }

  async function syncSession(authHeader) {
    if (!authHeader || !state.secret) return;
    const token = authHeader.replace(/^Bearer\s+/i, "").trim();
    if (!token || token === state.sessionToken) return;
    state.sessionToken = token;
    try {
      await fetch(SESSION_SYNC_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret: state.secret, session_token: token }),
      });
      log("session synced");
    } catch (e) {
      log("session sync failed", e);
    }
  }

  function tradeKey(row) {
    return String(row.id || row.alertId || row.signature || row.txHash || JSON.stringify(row).slice(0, 80));
  }

  async function forwardTrade(row) {
    const key = tradeKey(row);
    if (state.seen.has(key)) return;
    const usd = Number(row.amountUsd || row.usd || row.totalUsd || 0);
    if (usd && usd < state.minUsd) return;

    const wallet = row.wallet || {};
    const token = row.token || {};
    const payload = {
      secret: state.secret,
      event_type: "trade",
      symbol: row.symbol || token.symbol || token.ticker || "UNKNOWN",
      action: (row.side || row.action || row.type || "buy").toLowerCase(),
      wallet_address: wallet.address || row.walletAddress || row.address || "",
      wallet_label: wallet.label || wallet.name || row.walletLabel || "",
      wallet_rank: row.walletRank || wallet.rank,
      chain: row.chain || "solana",
      amount_usd: usd,
      token_address: token.mint || token.address || row.mint || "",
      wallets_watching: row.walletsWatching || 8,
      message: row.message || row.content || "",
      url: row.id ? `axiom:trade:${row.id}` : undefined,
    };

    try {
      const res = await fetch(state.webhookUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      state.seen.add(key);
      state.sent += 1;
      saveConfig();
      log("forwarded", payload.symbol, payload.action);
    } catch (e) {
      state.errors += 1;
      log("forward error", e);
    }
  }

  function extractRows(payload) {
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== "object") return [];
    for (const key of ["trades", "items", "data", "results", "feed", "activity", "alerts"]) {
      if (Array.isArray(payload[key])) return payload[key];
    }
    return [];
  }

  const origFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await origFetch.apply(this, args);
    try {
      const url = String(args[0] || "");
      const init = args[1] || {};
      const auth = (init.headers && (init.headers.Authorization || init.headers.authorization)) || "";
      if (auth) syncSession(auth);
      if (url.includes("axiom.trade") && /trade|feed|alert|wallet/i.test(url)) {
        const clone = response.clone();
        clone
          .json()
          .then((data) => extractRows(data).forEach((row) => forwardTrade(row)))
          .catch(() => {});
      }
    } catch (_) {}
    return response;
  };

  GM_registerMenuCommand("Apex axiom bridge: configure secret", () => {
    const secret = prompt("TradingView webhook secret (TRADINGVIEW_WEBHOOK_SECRET):", state.secret || "");
    if (secret !== null) {
      state.secret = secret.trim();
      saveConfig();
      alert("Secret saved. Keep axiom.trade tab open for 24/7 forwarding.");
    }
  });

  loadConfig();
  log("axiom bridge ready");
})();
