# fomo.family → Apex Trading (Zapier bridge)

Forward fomo alerts into the Apex crypto bot when you cannot keep a browser tab open.

**Webhook target**

```
POST https://apex-trading-backend.onrender.com/api/webhooks/fomo
Content-Type: application/json
```

**Body template** (replace `YOUR_SECRET`):

```json
{
  "secret": "YOUR_SECRET",
  "event_type": "trade",
  "symbol": "{{symbol}}",
  "action": "{{action}}",
  "trader_name": "{{trader_name}}",
  "trader_rank": {{trader_rank}},
  "trader_pnl_pct": {{trader_pnl_pct}},
  "chain": "{{chain}}",
  "amount_usd": {{amount_usd}},
  "message": "{{message}}"
}
```

---

## Option A — Email Parser (best for email alerts)

Use when fomo (or your mail client) sends trade notification emails.

1. In Zapier, create a Zap:
   - **Trigger:** Email Parser by Zapier → New Email
   - Copy your unique `@robot.zapier.com` address
2. Forward or filter fomo notification emails to that address
3. In Email Parser (parser.zapier.com), teach fields:
   - `symbol` — token ticker (e.g. WIF)
   - `action` — buy / sell
   - `trader_name` — username from subject/body
   - `amount_usd` — dollar size if present
4. **Action:** Webhooks by Zapier → POST
   - URL: `https://apex-trading-backend.onrender.com/api/webhooks/fomo`
   - Payload type: JSON
   - Map parser fields into the body template above
   - Hard-code `"secret": "YOUR_SECRET"`

**Gmail variant:** Trigger = Gmail → New Email (search: `from:fomo OR subject:fomo`), then Formatter → Text → Extract pattern, then Webhooks POST.

---

## Option B — iOS Shortcut → Zapier Catch Hook (mobile push)

fomo push notifications do not natively hit Zapier. Bridge with Shortcuts:

1. Zapier → **Webhooks by Zapier** → Catch Hook → copy hook URL
2. Add a second step: **Webhooks by Zapier** → POST to Apex fomo webhook with JSON body (map fields from step 1)
3. On iPhone: Shortcuts → Automation → When I receive a notification from **fomo**
4. Action: Get contents of URL (POST hook URL) with JSON:
   - `symbol`, `action`, `trader_name`, `message` parsed from notification text (use Split Text / Match)

Run the Shortcut manually first to confirm Zapier receives the payload, then enable automation.

---

## Option C — Manual replay while tuning traders

Use repo scripts (no Zapier):

```bash
# Smoke test
./scripts/fomo-test-webhook.sh WIF buy 3

# Manual alert (symbol action trader rank usd chain message)
./scripts/fomo-send-alert.sh WIF buy legend_trader 5 5000 solana "Top trader buy"
```

---

## Field reference

| Field | Required | Notes |
|-------|----------|-------|
| `secret` | yes | Same as `TRADINGVIEW_WEBHOOK_SECRET` on Render |
| `symbol` | yes | Ticker: WIF, PEPE, BONK (auto-maps to USDT pair) |
| `action` | yes | `buy` or `sell` |
| `trader_name` | recommended | Display name / handle |
| `trader_rank` | recommended | Leaderboard rank → higher bot relevance |
| `trader_pnl_pct` | optional | Boosts relevance when >50% |
| `amount_usd` | optional | Filters noise; bridge default min $250 |
| `chain` | optional | solana, base, bnb, monad |

---

## Verify in Apex

- CRM platform status shows **fomo.family webhook ready**
- Intel source `fomo` appears in `/api/intelligence/sources`
- Crypto bot may add hot symbols from recent fomo buys
