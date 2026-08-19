from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://uscode:uscode@localhost:5432/uscode"

    # Connection pooling (ADR-0073). The defaults SQLAlchemy ships — 5
    # connections, 10 overflow, a 30-second wait for one — are what the site
    # was running on when a crawl held all fifteen open and every request
    # queued behind them for longer than the proxy was willing to wait.
    #
    # `db_pool_timeout` is the one that changed character rather than size: a
    # request that cannot get a connection within it fails, and failing in two
    # seconds is a 500 the reader sees and the proxy logs, while failing in
    # thirty is a request still occupying a worker thread long after the
    # client gave up. Shedding is the point.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 2
    db_pool_recycle: int = 1800

    # Statement and transaction bounds for API request sessions, in
    # milliseconds; `storage/session.py` applies them per transaction so that
    # ingest, which shares this engine module in its own process, keeps the
    # unbounded budget its bulk loads need.
    #
    # `db_idle_in_transaction_timeout_ms` is the specific defence against what
    # took the site down: fifteen backends sitting `idle in transaction` on
    # `ClientRead`, each holding a pooled connection for a request that would
    # never return. Postgres now ends those itself.
    db_statement_timeout_ms: int = 20_000
    db_idle_in_transaction_timeout_ms: int = 30_000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
