# TradingView Webhook Setup

A webhook secret **nem TradingView-től jön** — te generálod, és ugyanazt a szöveget kell beírnod az alert JSON-ba és a backend `.env`-be is.

## 1. Backend secret (már beállítva)

```
TRADINGVIEW_WEBHOOK_SECRET=apex_tv_EB9nj4sZ_8nZCIYY-38U8ci4IodUX4G2
```

Production backend (Render/Railway) env var-ban is add hozzá ugyanezt.

## 2. Webhook URL

Ha a backend fut (pl. Render):

```
https://YOUR-BACKEND.onrender.com/api/webhooks/tradingview
```

Local teszt:

```
http://localhost:8000/api/webhooks/tradingview
```

## 3. TradingView alert beállítás

Minden alertnél:

1. TradingView → chart → **Alert** (harang ikon)
2. **Notifications** → pipáld: **Webhook URL**
3. Webhook URL: fenti backend URL
4. **Message** mező (JSON — másold be, cseréld a symbol/action értékeket):

```json
{
  "secret": "apex_tv_EB9nj4sZ_8nZCIYY-38U8ci4IodUX4G2",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.action}}",
  "message": "Alert on {{ticker}} at {{close}}"
}
```

Strategy nélküli egyszerű alert:

```json
{
  "secret": "apex_tv_EB9nj4sZ_8nZCIYY-38U8ci4IodUX4G2",
  "symbol": "{{ticker}}",
  "action": "buy",
  "message": "Manual alert {{ticker}} {{interval}}"
}
```

5. **Create** → alert kész.

## 4. Ellenőrzés

Dashboard → **Intelligence** tab → `tradingview` forrás **active** lesz, amikor érkezik az első alert.

API teszt (curl):

```bash
curl -X POST https://YOUR-BACKEND/api/webhooks/tradingview \
  -H "Content-Type: application/json" \
  -d '{"secret":"apex_tv_EB9nj4sZ_8nZCIYY-38U8ci4IodUX4G2","symbol":"BTCUSDT","action":"buy","message":"test"}'
```

Válasz: `{"status":"received","symbol":"BTCUSDT","action":"buy"}`
