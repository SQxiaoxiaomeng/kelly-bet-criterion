from dataclasses import dataclass
from decimal import Decimal

from app.providers.base import RawDailyBar


@dataclass(frozen=True)
class DataQualityResult:
    is_valid: bool
    reason: str | None = None


def validate_daily_bar(bar: RawDailyBar) -> DataQualityResult:
    if bar.volume < Decimal("0"):
        return DataQualityResult(False, "NEGATIVE_VOLUME")
    if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
        return DataQualityResult(False, "INVALID_OHLC_RANGE")
    if bar.low > bar.high:
        return DataQualityResult(False, "LOW_GREATER_THAN_HIGH")
    return DataQualityResult(True)
