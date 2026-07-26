from collections.abc import Callable
from datetime import UTC, date, datetime, time
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.backtest import DailyBar
from app.infrastructure.models import InstrumentModel, MarketBarModel


class SqlAlchemyMarketDataReader:
    """Reads immutable, quality-approved daily bars and names their exact input snapshot."""

    def __init__(self, session_factory: Callable[[], Session], source: str) -> None:
        self._session_factory = session_factory
        self._source = source

    def read_daily_bars(self, symbol: str, start: date, end: date) -> tuple[list[DailyBar], str]:
        exchange, code = _split_symbol(symbol)
        start_at = datetime.combine(start, time.min, tzinfo=UTC)
        end_at = datetime.combine(end, time.max, tzinfo=UTC)
        with self._session_factory() as session:
            records = list(
                session.scalars(
                    select(MarketBarModel)
                    .join(InstrumentModel, MarketBarModel.instrument_id == InstrumentModel.id)
                    .where(
                        InstrumentModel.exchange == exchange,
                        InstrumentModel.symbol == code,
                        MarketBarModel.timeframe == "1d",
                        MarketBarModel.source == self._source,
                        MarketBarModel.quality_status == "VALID",
                        MarketBarModel.timestamp >= start_at,
                        MarketBarModel.timestamp <= end_at,
                    )
                    .order_by(MarketBarModel.timestamp)
                )
            )
        input_ids = ",".join(str(record.id) for record in records)
        snapshot_hash = sha256(input_ids.encode()).hexdigest()[:16]
        snapshot_id = f"market-bars:{self._source}:{snapshot_hash}"
        return (
            [
                DailyBar(
                    trade_date=record.timestamp.date(),
                    open=record.open,
                    high=record.high,
                    low=record.low,
                    close=record.close,
                    volume=record.volume,
                )
                for record in records
            ],
            snapshot_id,
        )


def _split_symbol(qualified_symbol: str) -> tuple[str, str]:
    try:
        exchange, code = qualified_symbol.split(":", maxsplit=1)
    except ValueError as exc:
        raise ValueError("INVALID_SYMBOL_FORMAT") from exc
    if exchange not in {"SSE", "SZSE", "BSE"} or not code:
        raise ValueError("INVALID_SYMBOL_FORMAT")
    return exchange, code
