from datetime import date
from decimal import Decimal
from pathlib import Path

from app.providers.fixture_provider import FixtureMarketDataProvider
from app.providers.quality import validate_daily_bar


def test_fixture_provider_filters_and_returns_normalizable_bars() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    provider = FixtureMarketDataProvider(fixture_path)

    bars = provider.fetch_daily_bars(
        symbols=["SSE:600000"],
        start=date(2026, 7, 24),
        end=date(2026, 7, 24),
    )

    assert provider.name == "fixture"
    assert len(bars) == 1
    assert bars[0].close == Decimal("10.25")
    assert validate_daily_bar(bars[0]).is_valid


def test_fixture_provider_derives_explicit_open_sessions() -> None:
    fixture_path = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    sessions = FixtureMarketDataProvider(fixture_path).fetch_trading_calendar(
        "SSE", date(2026, 7, 16), date(2026, 7, 24)
    )

    assert len(sessions) == 7
    assert all(session.is_open for session in sessions)
