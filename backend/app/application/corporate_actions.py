from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.application.data_imports import _split_symbol
from app.infrastructure.models import CorporateActionModel, InstrumentModel
from app.providers.base import MarketDataProvider


@dataclass(frozen=True)
class CorporateActionImportResult:
    imported_count: int
    duplicate_count: int


class CorporateActionImportService:
    """Imports normalized dividends without exposing provider SDKs to trading logic."""

    def __init__(
        self, session_factory: sessionmaker[Session], provider: MarketDataProvider
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider

    def sync_cash_dividends(
        self, symbols: list[str], start: date, end: date
    ) -> CorporateActionImportResult:
        if not symbols:
            raise ValueError("SYMBOLS_REQUIRED")
        if start > end:
            raise ValueError("INVALID_DATE_RANGE")
        imported_count = 0
        duplicate_count = 0
        with self._session_factory() as session:
            for dividend in self._provider.fetch_cash_dividends(symbols, start, end):
                exchange, symbol = _split_symbol(dividend.symbol)
                instrument = session.scalar(
                    select(InstrumentModel).where(
                        InstrumentModel.exchange == exchange, InstrumentModel.symbol == symbol
                    )
                )
                if instrument is None:
                    raise ValueError("INSTRUMENT_NOT_FOUND")
                existing = session.scalar(
                    select(CorporateActionModel.id).where(
                        CorporateActionModel.instrument_id == instrument.id,
                        CorporateActionModel.action_type == "CASH_DIVIDEND",
                        CorporateActionModel.ex_date == dividend.ex_date,
                        CorporateActionModel.source == self._provider.name,
                    )
                )
                if existing is not None:
                    duplicate_count += 1
                    continue
                session.add(
                    CorporateActionModel(
                        id=str(uuid4()), instrument_id=instrument.id, action_type="CASH_DIVIDEND",
                        ex_date=dividend.ex_date, cash_per_share=dividend.cash_per_share,
                        source=self._provider.name, published_at=dividend.published_at,
                        created_at=datetime.now(UTC),
                    )
                )
                imported_count += 1
            session.commit()
        return CorporateActionImportResult(imported_count, duplicate_count)
