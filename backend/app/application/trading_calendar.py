from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models import TradingCalendarModel
from app.providers.base import MarketDataProvider


@dataclass(frozen=True)
class CalendarSyncResult:
    imported_count: int
    updated_count: int


class TradingCalendarService:
    """Keeps exchange sessions explicit so scheduled settlement never guesses holidays."""

    def __init__(
        self, session_factory: sessionmaker[Session], provider: MarketDataProvider | None = None
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider

    def sync(self, exchange: str, start: date, end: date) -> CalendarSyncResult:
        if start > end:
            raise ValueError("INVALID_DATE_RANGE")
        if self._provider is None:
            raise ValueError("CALENDAR_PROVIDER_NOT_CONFIGURED")
        imported_count = 0
        updated_count = 0
        with self._session_factory() as session:
            for raw_day in self._provider.fetch_trading_calendar(exchange, start, end):
                existing = session.scalar(
                    select(TradingCalendarModel).where(
                        TradingCalendarModel.exchange == raw_day.exchange,
                        TradingCalendarModel.trade_date == raw_day.trade_date,
                    )
                )
                if existing is None:
                    session.add(
                        TradingCalendarModel(
                            exchange=raw_day.exchange,
                            trade_date=raw_day.trade_date,
                            is_open=raw_day.is_open,
                        )
                    )
                    imported_count += 1
                elif existing.is_open != raw_day.is_open:
                    existing.is_open = raw_day.is_open
                    updated_count += 1
            session.commit()
        return CalendarSyncResult(imported_count, updated_count)

    def is_open(self, exchange: str, trade_date: date) -> bool | None:
        with self._session_factory() as session:
            row = session.scalar(
                select(TradingCalendarModel.is_open).where(
                    TradingCalendarModel.exchange == exchange,
                    TradingCalendarModel.trade_date == trade_date,
                )
            )
            return row
