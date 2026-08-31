"use client";

import type { PlatformStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

type Integrations = NonNullable<PlatformStatus["integrations"]>;

export function IntegrationHooksPanel({
  integrations,
  backendOffline,
}: {
  integrations?: Integrations;
  backendOffline?: boolean;
}) {
  if (!integrations) {
    if (backendOffline) {
      return (
        <p className="text-xs text-apex-red border border-apex-red/30 bg-apex-red/10 rounded px-2 py-1.5">
          TradingView, Polymarket, and wallet hooks unavailable until Render billing is restored.
        </p>
      );
    }
    return (
      <p className="text-xs text-gray-500">
        No trading hooks configured yet — set TRADINGVIEW_WEBHOOK_SECRET on Render for
        TradingView, wallet, fomo, axiom, and Phantom bridges.
      </p>
    );
  }

  const hasAny =
    integrations.tradingview_webhook ||
    integrations.tradingview_setup ||
    integrations.polymarket_market_scanner ||
    integrations.polymarket_account_hook ||
    integrations.polymarket_api_key ||
    integrations.wallet_tracker_webhook ||
    integrations.wallet_tracker ||
    integrations.fomo_webhook ||
    integrations.fomo_family ||
    integrations.axiom_webhook ||
    integrations.axiom_trade ||
    integrations.phantom_webhook ||
    integrations.phantom_wallet;

  if (!hasAny) {
    return (
      <p className="text-xs text-gray-500">
        No trading hooks configured yet — set TRADINGVIEW_WEBHOOK_SECRET on Render for
        TradingView, wallet, fomo, axiom, and Phantom bridges.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {backendOffline ? (
        <p className="text-[10px] text-apex-red border border-apex-red/30 bg-apex-red/10 rounded px-2 py-1.5">
          Hook status cached from last /api/status — webhook delivery requires an online backend.
        </p>
      ) : null}
      {(integrations.tradingview_webhook || integrations.tradingview_setup) && (
        <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
          <p className="text-apex-gold font-medium mb-1">TradingView webhook ready</p>
          {integrations.tradingview_setup && <p>{integrations.tradingview_setup}</p>}
          {integrations.tradingview_webhook_url && (
            <p className="mt-1 font-mono text-[10px] text-gray-500 break-all">
              {integrations.tradingview_webhook_url}
            </p>
          )}
          {integrations.tradingview_test_endpoint && (
            <p className="mt-2 text-[10px] text-gray-500">
              Test: {integrations.tradingview_test_endpoint}
            </p>
          )}
          {integrations.tradingview_items != null && integrations.tradingview_items > 0 && (
            <p className="mt-1 text-apex-green text-[10px]">
              {integrations.tradingview_items} alert(s) received
            </p>
          )}
          {integrations.tradingview_example_payload && (
            <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
              {JSON.stringify(integrations.tradingview_example_payload, null, 2)}
            </pre>
          )}
        </div>
      )}
      {(integrations.polymarket_market_scanner ||
        integrations.polymarket_account_hook ||
        integrations.polymarket_api_key) && (
        <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
          <p className="text-apex-gold font-medium mb-1">
            Polymarket{" "}
            {integrations.polymarket_account_hook && integrations.polymarket_api_key
              ? "account hook + market scanner"
              : integrations.polymarket_account_hook
                ? "account hook"
                : integrations.polymarket_api_key
                  ? "market scanner"
                  : "scanner ready (configure API key + wallet)"}
          </p>
          {integrations.polymarket_profile_url && (
            <p className="mt-1 text-[10px]">
              <a
                href={integrations.polymarket_profile_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-apex-gold hover:underline break-all"
              >
                {integrations.polymarket_profile_url}
              </a>
            </p>
          )}
          <div className="mt-1 flex flex-wrap gap-2 text-[10px]">
            <span
              className={cn(
                "px-2 py-0.5 rounded-full",
                integrations.polymarket_api_key
                  ? "bg-apex-green/10 text-apex-green"
                  : "bg-gray-800 text-gray-500"
              )}
            >
              API key {integrations.polymarket_api_key ? "on" : "off"}
            </span>
            <span
              className={cn(
                "px-2 py-0.5 rounded-full",
                integrations.polymarket_account_hook
                  ? "bg-apex-green/10 text-apex-green"
                  : "bg-gray-800 text-gray-500"
              )}
            >
              Account hook {integrations.polymarket_account_hook ? "on" : "off"}
            </span>
            <span className="px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300">
              Scanner always on
            </span>
          </div>
          {((integrations.polymarket_intel_items != null && integrations.polymarket_intel_items > 0) ||
            (integrations.polymarket_account_items != null &&
              integrations.polymarket_account_items > 0)) && (
            <p className="mt-1 text-apex-green text-[10px]">
              {integrations.polymarket_intel_items ?? 0} market intel ·{" "}
              {integrations.polymarket_account_items ?? 0} account hook
            </p>
          )}
          {integrations.polymarket_setup && (
            <p className="mt-1 text-[10px] text-gray-500">{integrations.polymarket_setup}</p>
          )}
          <p className="mt-1 text-[10px] text-gray-500">
            Macro prediction markets feed the polymarket bot; account hook mirrors linked wallet
            positions into intel.
          </p>
        </div>
      )}
      {(integrations.wallet_tracker_webhook || integrations.wallet_tracker) && (
        <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
          <p className="text-apex-gold font-medium mb-1">
            Wallet tracker {integrations.wallet_tracker ? "active" : "webhook ready"}
          </p>
          {integrations.wallet_tracker_webhook_url && (
            <p className="font-mono text-[10px] text-gray-500 break-all">
              {integrations.wallet_tracker_webhook_url}
            </p>
          )}
          <p className="mt-1 text-[10px] text-gray-500">
            On-chain whale scan + external monitor ingest (Arkham, Nansen, custom)
          </p>
          {integrations.wallet_tracker_example_payload && (
            <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
              {JSON.stringify(integrations.wallet_tracker_example_payload, null, 2)}
            </pre>
          )}
        </div>
      )}
      {(integrations.fomo_webhook || integrations.fomo_family) && (
        <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
          <p className="text-apex-gold font-medium mb-1">
            fomo.family {integrations.fomo_webhook ? "webhook ready" : "enabled"}
          </p>
          {integrations.fomo_webhook_url && (
            <p className="font-mono text-[10px] text-gray-500 break-all">
              {integrations.fomo_webhook_url}
            </p>
          )}
          {integrations.fomo_userscript_url && (
            <p className="mt-1 text-[10px]">
              <a
                href={integrations.fomo_userscript_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-apex-gold hover:underline break-all"
              >
                Install userscript (Tampermonkey v1.1 — auto-syncs bearer)
              </a>
            </p>
          )}
          {integrations.fomo_bearer_configured && (
            <p
              className={cn(
                "mt-1 text-[10px]",
                integrations.fomo_bearer_polling_active ? "text-green-400" : "text-amber-400"
              )}
            >
              Server poll:{" "}
              {integrations.fomo_bearer_polling_active
                ? `active (${integrations.fomo_bearer_minutes_remaining ?? "?"} min left)`
                : "bearer expired — keep fomo.family open in Tampermonkey or refresh token"}
            </p>
          )}
          {integrations.fomo_webhook_fallback_active && (
            <p className="mt-1 text-[10px] text-blue-400">
              Webhook fallback active — Tampermonkey bridge still ingests trades
            </p>
          )}
          {integrations.fomo_setup && (
            <p className="mt-1 text-[10px] text-gray-500">{integrations.fomo_setup}</p>
          )}
          {integrations.fomo_bridge_scripts && (
            <ul className="mt-2 text-[10px] text-gray-500 list-disc list-inside space-y-1">
              <li>
                Userscript: <code>{integrations.fomo_bridge_scripts.userscript}</code>
              </li>
              <li>
                Zapier: <code>{integrations.fomo_bridge_scripts.zapier_guide}</code>
              </li>
              <li>
                Manual curl: <code>{integrations.fomo_bridge_scripts.manual_curl}</code>
              </li>
            </ul>
          )}
          {integrations.fomo_example_payload && (
            <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
              {JSON.stringify(integrations.fomo_example_payload, null, 2)}
            </pre>
          )}
        </div>
      )}
      {(integrations.axiom_webhook || integrations.axiom_trade) && (
        <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
          <p className="text-apex-gold font-medium mb-1">
            axiom.trade{" "}
            {integrations.axiom_multi_wallet_ready
              ? `multi-wallet (${integrations.axiom_tracked_wallets ?? 8}+)`
              : integrations.axiom_webhook
                ? "webhook ready"
                : "enabled"}
          </p>
          {integrations.axiom_webhook_url && (
            <p className="font-mono text-[10px] text-gray-500 break-all">
              {integrations.axiom_webhook_url}
            </p>
          )}
          {integrations.axiom_userscript_url && (
            <p className="mt-1 text-[10px]">
              <a
                href={integrations.axiom_userscript_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-apex-gold hover:underline break-all"
              >
                Install axiom userscript (24/7 memecoin + wallet bridge)
              </a>
            </p>
          )}
          {integrations.axiom_trade && (
            <p className="mt-1 text-[10px] text-gray-400">
              Poll mode:{" "}
              <span
                className={cn(
                  integrations.axiom_poll_mode === "session"
                    ? "text-green-400"
                    : integrations.axiom_poll_mode === "mirror"
                      ? "text-blue-400"
                      : "text-amber-400"
                )}
              >
                {integrations.axiom_poll_mode ?? "off"}
              </span>
              {integrations.axiom_poll_mode === "mirror"
                ? " — mirroring wallet_tracker + phantom holdings"
                : ""}
            </p>
          )}
          {integrations.axiom_session_configured && (
            <p
              className={cn(
                "mt-1 text-[10px]",
                integrations.axiom_session_polling_active ? "text-green-400" : "text-amber-400"
              )}
            >
              Session poll:{" "}
              {integrations.axiom_session_polling_active
                ? "active"
                : "expired — keep axiom.trade open in Tampermonkey"}
            </p>
          )}
          {integrations.axiom_setup && (
            <p className="mt-1 text-[10px] text-gray-500">{integrations.axiom_setup}</p>
          )}
          {integrations.axiom_example_payload && (
            <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
              {JSON.stringify(integrations.axiom_example_payload, null, 2)}
            </pre>
          )}
        </div>
      )}
      {(integrations.phantom_webhook || integrations.phantom_wallet) && (
        <div className="rounded-lg border border-apex-border bg-apex-dark px-3 py-2 text-xs text-gray-400">
          <p className="text-apex-gold font-medium mb-1">
            Phantom wallet {integrations.phantom_webhook ? "webhook ready" : "enabled"}
          </p>
          {integrations.phantom_webhook_url && (
            <p className="font-mono text-[10px] text-gray-500 break-all">
              {integrations.phantom_webhook_url}
            </p>
          )}
          {integrations.phantom_userscript_url && (
            <p className="mt-1 text-[10px]">
              <a
                href={integrations.phantom_userscript_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-apex-gold hover:underline break-all"
              >
                Install Phantom userscript (portfolio forwarding)
              </a>
            </p>
          )}
          {integrations.phantom_portfolio_poll ? (
            <p className="mt-1 text-[10px] text-green-400">
              Server portfolio poll active
              {integrations.phantom_portfolio_poll_mode
                ? ` (${integrations.phantom_portfolio_poll_mode})`
                : ""}
              {integrations.phantom_tracked_wallets
                ? ` — ${integrations.phantom_tracked_wallets} wallets`
                : ""}
            </p>
          ) : (
            <p className="mt-1 text-[10px] text-amber-400">
              Portfolio poll inactive
              {integrations.phantom_portfolio_poll_mode
                ? ` (${integrations.phantom_portfolio_poll_mode})`
                : ""}
              {" — "}
              set HELIUS_API_KEY or install Phantom userscript
            </p>
          )}
          {integrations.phantom_setup && (
            <p className="mt-1 text-[10px] text-gray-500">{integrations.phantom_setup}</p>
          )}
          {integrations.phantom_example_payload && (
            <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] text-gray-400 overflow-x-auto">
              {JSON.stringify(integrations.phantom_example_payload, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
