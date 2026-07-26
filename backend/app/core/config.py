from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parents[3] / ".env",
        extra="ignore",
    )

    app_name: str = "a-share-quant-lab"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://a_share_quant:change-me-for-local-use@localhost:5432/a_share_quant_lab"
    redis_url: str = "redis://localhost:6379/0"
    backtest_repository: str = "memory"
    backtest_market_data: str = "fixture"
    task_execution_mode: str = "celery"
    market_data_provider: str = "fixture"
    tushare_token: str | None = None
    max_order_notional: Decimal = Decimal("1000000")
    max_single_position_ratio: Decimal = Decimal("0.50")
    max_total_position_ratio: Decimal = Decimal("0.95")


@lru_cache
def get_settings() -> Settings:
    return Settings()
