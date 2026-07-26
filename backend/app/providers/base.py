from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class RawDailyBar:
    symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    amount: Decimal | None
    published_at: datetime | None


@dataclass(frozen=True)
class RawInstrument:
    symbol: str
    name: str
    board: str = "UNKNOWN"


@dataclass(frozen=True)
class RawTradingDay:
    exchange: str
    trade_date: date
    is_open: bool


@dataclass(frozen=True)
class RawCashDividend:
    symbol: str
    ex_date: date
    cash_per_share: Decimal
    published_at: datetime | None


class MarketDataProvider(Protocol):
    name: str

    def fetch_instruments(self, symbols: list[str]) -> list[RawInstrument]: ...

    def fetch_daily_bars(self, symbols: list[str], start: date, end: date) -> list[RawDailyBar]: ...

    def fetch_trading_calendar(
        self, exchange: str, start: date, end: date
    ) -> list[RawTradingDay]: ...

    def fetch_cash_dividends(
        self, symbols: list[str], start: date, end: date
    ) -> list[RawCashDividend]: ...
