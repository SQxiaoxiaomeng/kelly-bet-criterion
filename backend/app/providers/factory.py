from pathlib import Path

from app.core.config import Settings
from app.providers.base import MarketDataProvider
from app.providers.fixture_provider import FixtureMarketDataProvider
from app.providers.tushare_provider import TushareMarketDataProvider


def create_market_data_provider(settings: Settings) -> MarketDataProvider:
    """Create the configured provider without leaking provider details into domain code."""
    if settings.market_data_provider == "fixture":
        fixture_path = Path(__file__).parents[2] / "tests" / "fixtures" / "daily_bars.json"
        return FixtureMarketDataProvider(fixture_path)
    if settings.market_data_provider == "tushare":
        return TushareMarketDataProvider(settings.tushare_token or "")
    raise ValueError("UNSUPPORTED_MARKET_DATA_PROVIDER")
