from datetime import date
from decimal import Decimal

from app.providers.base import RawDailyBar
from app.providers.quality import validate_daily_bar


def test_rejects_daily_bar_with_invalid_ohlc_range() -> None:
    bar = RawDailyBar(
        symbol="SSE:600000",
        trade_date=date(2026, 7, 24),
        open=Decimal("10.00"),
        high=Decimal("10.10"),
        low=Decimal("9.90"),
        close=Decimal("10.50"),
        volume=Decimal("1000"),
        amount=None,
        published_at=None,
    )

    result = validate_daily_bar(bar)

    assert not result.is_valid
    assert result.reason == "INVALID_OHLC_RANGE"
