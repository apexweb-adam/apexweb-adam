"""Database pool configuration for Supabase session mode."""

from app.database import _engine_kwargs, normalize_database_url


def test_postgres_engine_uses_small_pool():
  url = "postgresql://user:pass@aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
  kwargs = _engine_kwargs(url)
  assert kwargs["pool_size"] == 5
  assert kwargs["max_overflow"] == 3
  assert kwargs["pool_timeout"] == 20
  assert kwargs["pool_pre_ping"] is True
  assert kwargs["pool_recycle"] == 280
  assert kwargs["connect_args"] == {"ssl": "require"}


def test_sqlite_engine_uses_null_pool():
  kwargs = _engine_kwargs("sqlite+aiosqlite:///data/test.db")
  from sqlalchemy.pool import NullPool

  assert kwargs["poolclass"] is NullPool


def test_normalize_database_url_asyncpg():
  assert normalize_database_url("postgres://x").startswith("postgresql+asyncpg://")
