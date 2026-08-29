// ==UserScript==
// @name         Apex fomo.family → Apex Trading Bridge
// @namespace    https://apex-trading-backend.onrender.com
// @version      1.0.0
// @description  Forward fomo.family feed/trade API events to Apex crypto intel webhook
// @match        https://fomo.family/*
// @match        https://*.fomo.family/*
// @match        https://app.fomo.family/*
// @match        https://production.fomo.family/*
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_registerMenuCommand
// @run-at       document-start
// ==/UserScript==

(function () {
  "use strict";

  const STORAGE_KEY = "apex_fomo_bridge_v1";
  const DEFAULT_WEBHOOK =
    "https://apex-trading-backend.onrender.com/api/webhooks/fomo";
  const API_HOST = "prod-api.fomo.family";
  const SEEN_MAX = 500;

  const CHAIN_BY_NETWORK = {
    1399811149: "solana",
    8453: "base",
    56: "bnb",
    143: "monad",
    4663: "robinhood",
    1: "ethereum",
  };

  const state = {
    webhookUrl: DEFAULT_WEBHOOK,
    secret: "",
    minUsd: 250,
    pollEnabled: true,
    pollSeconds: 15,
    debug: false,
    bearer: "",
    seen: new Set(),
    sent: 0,
    errors: 0,
    lastSentAt: null,
    pollTimer: null,
  };

  function loadConfig() {
    try {
      const raw = GM_getValue(STORAGE_KEY, "{}");
      const cfg = typeof raw === "string" ? JSON.parse(raw) : raw;
      Object.assign(state, cfg);
      if (!Array.isArray(state.seen)) state.seen = [];
      state.seen = new Set(state.seen.slice(-SEEN_MAX));
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
        pollEnabled: state.pollEnabled,
        pollSeconds: state.pollSeconds,
        debug: state.debug,
        seen: Array.from(state.seen).slice(-SEEN_MAX),
      })
    );
  }

  function log(...args) {
    if (state.debug) console.log("[apex-fomo-bridge]", ...args);
  }

  function networkToChain(networkId) {
    const id = Number(networkId);
    return CHAIN_BY_NETWORK[id] || `chain_${id || "unknown"}`;
  }

  function pickAction(trade) {
    const raw = String(
      trade.side ||
        trade.action ||
        trade.type ||
        trade.direction ||
        trade.tradeType ||
        ""
    ).toLowerCase();
    if (/sell|short|close|exit|dump/.test(raw)) return "sell";
    if (/buy|long|open|enter|accum|ape/.test(raw)) return "buy";
    if (trade.isBuy === false || trade.isSell === true) return "sell";
    if (trade.isBuy === true || trade.isSell === false) return "buy";
    return "buy";
  }

  function pickUsd(trade) {
    const candidates = [
      trade.totalUsd,
      trade.amountUsd,
      trade.usdValue,
      trade.notionalUsd,
      trade.valueUsd,
      trade.totalUsdc,
      trade.usd,
    ];
    for (const v of candidates) {
      const n = Number(v);
      if (Number.isFinite(n) && n > 0) return n;
    }
    return 0;
  }

  function pickSymbol(trade) {
    const token = trade.token || trade.asset || trade.coin || {};
    return String(
      trade.symbol ||
        trade.tokenSymbol ||
        token.symbol ||
        trade.ticker ||
        trade.name ||
        "UNKNOWN"
    )
      .replace(/^\$/, "")
      .trim();
  }

  function pickTrader(trade) {
    const user = trade.user || trade.trader || trade.profile || {};
    return {
      id: String(user.id || user.userId || trade.userId || "").trim(),
      name: String(
        user.handle ||
          user.username ||
          user.displayName ||
          user.name ||
          trade.userHandle ||
          trade.traderName ||
          "fomo_trader"
      ).trim(),
      rank: Number(user.rank || trade.userRank || trade.rank || 0) || null,
      pnl_pct: Number(user.pnlPct || user.pnl || trade.pnlPct || 0) || null,
    };
  }

  function tradeId(trade) {
    return String(
      trade.id ||
        trade.tradeId ||
        trade.uuid ||
        `${pickTrader(trade).id}:${pickSymbol(trade)}:${pickAction(trade)}:${trade.openedAt || trade.createdAt || ""}`
    );
  }

  function normalizeTrades(payload) {
    if (!payload) return [];
    if (Array.isArray(payload)) return payload;
    const keys = ["trades", "items", "data", "results", "feed", "activity"];
    for (const key of keys) {
      if (Array.isArray(payload[key])) return payload[key];
    }
    if (payload.trade && typeof payload.trade === "object") return [payload.trade];
    return [];
  }

  function toWebhookPayload(trade) {
    const symbol = pickSymbol(trade);
    const action = pickAction(trade);
    const amountUsd = pickUsd(trade);
    const trader = pickTrader(trade);
    const token = trade.token || trade.asset || {};
    const tokenAddress = String(
      trade.tokenAddress ||
        trade.mint ||
        token.address ||
        trade.contractAddress ||
        ""
    ).trim();
    const networkId = Number(
      trade.networkId || trade.chainId || token.networkId || token.chainId || 0
    );
    const id = tradeId(trade);

    return {
      secret: state.secret,
      event_type: "trade",
      symbol,
      action,
      trader_id: trader.id,
      trader_name: trader.name,
      trader_rank: trader.rank,
      trader_pnl_pct: trader.pnl_pct,
      chain: networkToChain(networkId),
      amount_usd: amountUsd,
      token_address: tokenAddress,
      url: `fomo:trade:${id}`,
      alert_id: id,
      message: `${trader.name} ${action} ${symbol} on ${networkToChain(networkId)}`,
    };
  }

  async function postTrade(trade) {
    if (!state.secret) return;
    const id = tradeId(trade);
    if (state.seen.has(id)) return;

    const body = toWebhookPayload(trade);
    const amountUsd = Number(body.amount_usd || 0);
    if (amountUsd > 0 && amountUsd < state.minUsd) {
      log("skip small trade", id, amountUsd);
      return;
    }

    try {
      const res = await fetch(state.webhookUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "omit",
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(json.status || res.statusText);
      state.seen.add(id);
      state.sent += 1;
      state.lastSentAt = new Date().toISOString();
      saveConfig();
      updateHud();
      log("sent", body.symbol, body.action, json);
    } catch (err) {
      state.errors += 1;
      updateHud();
      console.warn("[apex-fomo-bridge] webhook error", err);
    }
  }

  function handlePayload(payload, source) {
    const trades = normalizeTrades(payload);
    if (!trades.length) return;
    log(`parsed ${trades.length} trades from ${source}`);
    for (const trade of trades) {
      postTrade(trade);
    }
  }

  function captureBearer(headers) {
    if (!headers) return;
    let auth = "";
    if (headers instanceof Headers) {
      auth = headers.get("Authorization") || headers.get("authorization") || "";
    } else if (typeof headers === "object") {
      auth =
        headers.Authorization ||
        headers.authorization ||
        headers.AUTHORIZATION ||
        "";
    }
    if (auth.startsWith("Bearer ") && auth.length > 20) {
      state.bearer = auth.slice(7);
    }
  }

  function shouldWatch(url) {
    try {
      const u = new URL(url, location.origin);
      return u.hostname.includes(API_HOST) || u.hostname.includes("fomo.family");
    } catch {
      return String(url).includes(API_HOST);
    }
  }

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function (...args) {
    const input = args[0];
    const init = args[1] || {};
    const url = typeof input === "string" ? input : input.url;
    captureBearer(init.headers);
    const response = await nativeFetch(...args);
    if (shouldWatch(url)) {
      try {
        const clone = response.clone();
        const contentType = clone.headers.get("content-type") || "";
        if (contentType.includes("json")) {
          const data = await clone.json();
          handlePayload(data, url);
        }
      } catch (err) {
        log("fetch parse error", err);
      }
    }
    return response;
  };

  const XHR = XMLHttpRequest.prototype;
  const open = XHR.open;
  const send = XHR.send;
  const setRequestHeader = XHR.setRequestHeader;

  XHR.open = function (method, url, ...rest) {
    this._apexUrl = url;
    this._apexHeaders = {};
    return open.call(this, method, url, ...rest);
  };

  XHR.setRequestHeader = function (name, value) {
    this._apexHeaders[name] = value;
    if (/authorization/i.test(name) && String(value).startsWith("Bearer ")) {
      state.bearer = String(value).slice(7);
    }
    return setRequestHeader.call(this, name, value);
  };

  XHR.send = function (...args) {
    this.addEventListener("load", function () {
      const url = this._apexUrl || "";
      if (!shouldWatch(url)) return;
      try {
        const contentType = this.getResponseHeader("content-type") || "";
        if (!contentType.includes("json")) return;
        const data = JSON.parse(this.responseText);
        handlePayload(data, url);
      } catch (err) {
        log("xhr parse error", err);
      }
    });
    return send.apply(this, args);
  };

  async function pollTrades() {
    if (!state.pollEnabled || !state.bearer || !state.secret) return;
    const url = `https://${API_HOST}/trades?limit=25`;
    try {
      const res = await nativeFetch(url, {
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${state.bearer}`,
          Origin: "https://fomo.family",
          Referer: "https://fomo.family/",
        },
        credentials: "omit",
      });
      if (!res.ok) return;
      const data = await res.json();
      handlePayload(data, "poll:/trades");
    } catch (err) {
      log("poll error", err);
    }
  }

  function restartPoll() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    if (!state.pollEnabled) return;
    const ms = Math.max(10, Number(state.pollSeconds) || 15) * 1000;
    state.pollTimer = setInterval(pollTrades, ms);
  }

  function updateHud() {
    const el = document.getElementById("apex-fomo-bridge-hud");
    if (!el) return;
    el.innerHTML = `
      <div style="font-weight:600;color:#f5c542;margin-bottom:4px;">Apex fomo bridge</div>
      <div>sent: ${state.sent} | errors: ${state.errors}</div>
      <div>secret: ${state.secret ? "set" : "missing"} | bearer: ${state.bearer ? "captured" : "waiting"}</div>
      <div>last: ${state.lastSentAt || "—"}</div>
    `;
  }

  function mountHud() {
    if (document.getElementById("apex-fomo-bridge-hud")) return;
    const panel = document.createElement("div");
    panel.id = "apex-fomo-bridge-hud";
    panel.style.cssText =
      "position:fixed;bottom:12px;right:12px;z-index:999999;background:#111827;color:#d1d5db;border:1px solid #374151;border-radius:8px;padding:10px 12px;font:11px/1.4 ui-monospace,Menlo,monospace;max-width:280px;box-shadow:0 8px 24px rgba(0,0,0,.35);";
    document.documentElement.appendChild(panel);
    updateHud();
  }

  function configure() {
    const webhookUrl = prompt("Apex fomo webhook URL", state.webhookUrl);
    if (webhookUrl === null) return;
    const secret = prompt("TRADINGVIEW_WEBHOOK_SECRET", state.secret);
    if (secret === null) return;
    const minUsd = prompt("Minimum trade USD to forward", String(state.minUsd));
    if (minUsd === null) return;
    const poll = confirm("Enable polling /trades with captured session bearer?");
    state.webhookUrl = webhookUrl.trim() || DEFAULT_WEBHOOK;
    state.secret = secret.trim();
    state.minUsd = Number(minUsd) || 250;
    state.pollEnabled = poll;
    saveConfig();
    restartPoll();
    updateHud();
    alert("Apex fomo bridge configured. Keep this fomo.family tab open while trading.");
  }

  loadConfig();

  GM_registerMenuCommand("Configure Apex fomo bridge", configure);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountHud);
  } else {
    mountHud();
  }

  restartPoll();
  setTimeout(pollTrades, 4000);
})();
