# Polymarket Integration

## Jelenlegi működés (account nélkül is)

A platform **nyilvános Polymarket Gamma API**-t használ — nincs szükség bejelentkezésre a piaci jelek olvasásához:

- Crypto, Trump, Fed, election piacok
- Automatikus scan 5 percenként
- Dashboard → Intelligence → `polymarket` forrás

## Bejelentkezés (opcionális)

Ha **saját pozícióid / wallet** alapján akarsz jelet (jövőbeli feature), Polymarket fiók kell:

1. Nyisd meg: https://polymarket.com
2. **Sign in** → email / Google / wallet
3. API kulcs jelenleg **nem kötelező** a read-only scannerhez

A jelenlegi bot **paper trading** módban nem kereskedik Polymarket-en — csak olvassa a prediction market odds-okat intelligencia jelként.
