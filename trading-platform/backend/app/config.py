from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Apex Trading Platform"
    database_url: str = "sqlite+aiosqlite:///./data/trading.db"
    paper_trading_only: bool = True
    initial_balance: float = 100_000.0

    # Market data
    binance_api_url: str = "https://api.binance.com/api/v3"

    # Intelligence (optional keys)
    newsapi_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    twitter_bearer_token: str = ""

    # Integrations
    tradingview_webhook_secret: str = ""
    polymarket_api_url: str = "https://gamma-api.polymarket.com"
    polymarket_data_api_url: str = "https://data-api.polymarket.com"
    polymarket_clob_api_url: str = "https://clob.polymarket.com"
    polymarket_api_key: str = ""
    polymarket_wallet_address: str = ""
    polymarket_deposit_address: str = ""
    polymarket_profile_url: str = "https://polymarket.com/@apexweb"
    polymarket_max_markets: int = 50
    polymarket_max_position_pct: float = 0.01
    polymarket_max_position_usd: float = 500.0
    polymarket_stop_loss_pct: float = 0.04
    polymarket_min_hold_seconds: int = 900
    polymarket_loss_cooldown_seconds: int = 3600
    polymarket_reentry_cooldown_seconds: int = 1800
    polymarket_max_open_positions: int = 5

    # Min hold before signal-based exit (stop-loss still immediate)
    crypto_min_hold_seconds: int = 300
    commodities_min_hold_seconds: int = 180
    crypto_loss_cooldown_seconds: int = 1800
    crypto_reentry_cooldown_seconds: int = 900
    commodities_loss_cooldown_seconds: int = 1200
    commodities_reentry_cooldown_seconds: int = 600
    stocks_loss_cooldown_seconds: int = 1800
    stocks_reentry_cooldown_seconds: int = 900

    # Bot tuning
    crypto_symbols: str = (
      "BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,PEPEUSDT,BNBUSDT,XRPUSDT,ADAUSDT,"
      "AVAXUSDT,LINKUSDT,MATICUSDT,SHIBUSDT,WIFUSDT,BONKUSDT"
    )
    stock_symbols: str = "AAPL,MSFT,NVDA,TSLA,SPY,QQQ"
    futures_symbols: str = "ES=F,NQ=F"
    commodity_symbols: str = "GC=F,SI=F,CL=F,EURUSD=X"

    # Learning
    min_win_rate_target: float = 0.55
    max_position_pct: float = 0.05
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04

    # Dashboard
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # Render injects these at build/deploy time (optional locally)
    render_git_commit: str = ""
    render_git_branch: str = ""

    class Config:
        env_file = (".env", "../.env")
        env_file_encoding = "utf-8"


settings = Settings()

BOT_TYPES = ["crypto", "stocks_futures", "commodities", "polymarket"]
