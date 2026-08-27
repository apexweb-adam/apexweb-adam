# Polymarket Integration

## Jelenlegi működés (account nélkül is)

A platform **nyilvános Polymarket Gamma API**-t használ — nincs szükség bejelentkezésre a piaci jelek olvasásához:

- Crypto, Trump, Fed, election piacok
- Automatikus scan 5 percenként
- Dashboard → Intelligence → `polymarket` forrás

## Bejelentkezés (opcionális)

Ha **saját pozícióid** alapján akarsz jelet, add meg a Polymarket **proxy wallet** címedet (nem kell API kulcs):

1. Nyisd meg: https://polymarket.com → Sign in
2. Profil → másold ki a wallet címet (0x...)
3. Add hozzá a `.env`-hez:

```
POLYMARKET_WALLET_ADDRESS=0xYourProxyWalletAddress
```

A bot olvassa a nyilvános Data API-t (`data-api.polymarket.com/positions`) — nincs szükség jelszóra vagy privát kulcsra.

Ha mégis be akarsz lépni: https://polymarket.com (Google / email / MetaMask).
