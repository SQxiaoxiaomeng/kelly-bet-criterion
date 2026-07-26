import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from app.providers.base import RawCashDividend, RawDailyBar, RawInstrument, RawTradingDay


class FixtureMarketDataProvider:
    """Deterministic provider used for M0 validation and automated tests."""

    name = "fixture"

    def __init__(self, fixture_path: Path) -> None:
        self._fixture_path = fixture_path

    def fetch_instruments(self, symbols: list[str]) -> list[RawInstrument]:
        return [
            RawInstrument(symbol=symbol, name=symbol.split(":", maxsplit=1)[-1])
            for symbol in symbols
        ]

    def fetch_daily_bars(self, symbols: list[str], start: date, end: date) -> list[RawDailyBar]:
        rows = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        requested_symbols = set(symbols)
        bars: list[RawDailyBar] = []
        for row in rows:
            trade_date = date.fromisoformat(row["trade_date"])
            if row["symbol"] not in requested_symbols or not start <= trade_date <= end:
                continue
            published_at = datetime.fromisoformat(row["published_at"]).replace(tzinfo=UTC)
            bars.append(
                RawDailyBar(
                    symbol=row["symbol"],
                    trade_date=trade_date,
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=Decimal(row["volume"]),
                    amount=Decimal(row["amount"]),
                    published_at=published_at,
                )
            )
        return bars

    def fetch_trading_calendar(
        self, exchange: str, start: date, end: date
    ) -> list[RawTradingDay]:
        if exchange not in {"SSE", "SZSE"}:
            raise ValueError("UNSUPPORTED_EXCHANGE")
        rows = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        return [
            RawTradingDay(exchange=exchange, trade_date=trade_date, is_open=True)
            for trade_date in sorted(
                {
                    date.fromisoformat(row["trade_date"])
                    for row in rows
                    if start <= date.fromisoformat(row["trade_date"]) <= end
                }
            )
        ]

    def fetch_cash_dividends(
        self, symbols: list[str], start: date, end: date
    ) -> list[RawCashDividend]:
        return []
