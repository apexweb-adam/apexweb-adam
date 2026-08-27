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

    # Bot tuning
    crypto_symbols: str = "BTCUSDT,ETHUSDT,SOLUSDT,DOGEUSDT,PEPEUSDT"
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

    class Config:
        env_file = (".env", "../.env")
        env_file_encoding = "utf-8"


settings = Settings()
