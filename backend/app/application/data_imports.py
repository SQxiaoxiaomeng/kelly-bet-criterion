import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models import DataImportJobModel, InstrumentModel, MarketBarModel
from app.providers.base import MarketDataProvider, RawDailyBar
from app.providers.quality import validate_daily_bar

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class DataImportResult:
    job_id: int
    imported_count: int
    duplicate_count: int
    invalid_count: int


class DataImportService:
    """Append-only daily-bar ingestion with an auditable import-job lifecycle."""

    def __init__(
        self, session_factory: sessionmaker[Session], provider: MarketDataProvider
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider

    def create_job(self) -> int:
        with self._session_factory() as session:
            job = DataImportJobModel(
                provider=self._provider.name,
                dataset="daily_bars",
                status="PENDING",
            )
            session.add(job)
            session.commit()
            return job.id

    def run_job(self, job_id: int, symbols: list[str], start: date, end: date) -> DataImportResult:
        if not symbols:
            raise ValueError("SYMBOLS_REQUIRED")
        if start > end:
            raise ValueError("INVALID_DATE_RANGE")

        with self._session_factory() as session:
            job = session.get(DataImportJobModel, job_id)
            if job is None:
                raise ValueError("DATA_IMPORT_JOB_NOT_FOUND")
            if job.status != "PENDING":
                raise ValueError("DATA_IMPORT_JOB_NOT_PENDING")
            job.status = "RUNNING"
            job.started_at = datetime.now(UTC)
            session.commit()

            try:
                self._sync_instrument_metadata(session, symbols)
                bars = self._provider.fetch_daily_bars(symbols, start, end)
                imported_count = 0
                duplicate_count = 0
                invalid_count = 0
                observed_at = datetime.now(UTC)
                for bar in bars:
                    quality = validate_daily_bar(bar)
                    if not quality.is_valid:
                        invalid_count += 1
                    if self._is_existing_bar(session, bar):
                        duplicate_count += 1
                        continue
                    instrument = self._get_or_create_instrument(session, bar.symbol)
                    session.add(
                        MarketBarModel(
                            instrument_id=instrument.id,
                            timeframe="1d",
                            timestamp=datetime.combine(bar.trade_date, time.min, tzinfo=UTC),
                            open=bar.open,
                            high=bar.high,
                            low=bar.low,
                            close=bar.close,
                            volume=bar.volume,
                            amount=bar.amount,
                            source=self._provider.name,
                            observed_at=observed_at,
                            published_at=bar.published_at,
                            quality_status="VALID" if quality.is_valid else "INVALID",
                        )
                    )
                    imported_count += 1

                job.status = "COMPLETED"
                job.finished_at = datetime.now(UTC)
                session.commit()
                return DataImportResult(job_id, imported_count, duplicate_count, invalid_count)
            except Exception as exc:
                session.rollback()
                failed_job = session.get(DataImportJobModel, job_id)
                if failed_job is not None:
                    failed_job.status = "FAILED"
                    failed_job.finished_at = datetime.now(UTC)
                    failed_job.error_message = str(exc)[:500]
                    session.commit()
                raise

    def run_full_history_job(self, job_id: int, symbol: str, end: date) -> DataImportResult:
        exchange, code = _split_symbol(symbol)
        with self._session_factory() as session:
            latest_timestamp = session.scalar(
                select(MarketBarModel.timestamp)
                .join(InstrumentModel, MarketBarModel.instrument_id == InstrumentModel.id)
                .where(
                    InstrumentModel.exchange == exchange,
                    InstrumentModel.symbol == code,
                    MarketBarModel.source == self._provider.name,
                    MarketBarModel.timeframe == "1d",
                )
                .order_by(MarketBarModel.timestamp.desc())
            )
        start = (
            latest_timestamp.date() + timedelta(days=1)
            if latest_timestamp
            else date(1990, 1, 1)
        )
        if start > end:
            with self._session_factory() as session:
                job = session.get(DataImportJobModel, job_id)
                if job is None:
                    raise ValueError("DATA_IMPORT_JOB_NOT_FOUND")
                if job.status != "PENDING":
                    raise ValueError("DATA_IMPORT_JOB_NOT_PENDING")
                now = datetime.now(UTC)
                job.status = "RUNNING"
                job.started_at = now
                session.commit()
                try:
                    self._sync_instrument_metadata(session, [symbol])
                    job.status = "COMPLETED"
                    job.finished_at = datetime.now(UTC)
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    failed_job = session.get(DataImportJobModel, job_id)
                    if failed_job is not None:
                        failed_job.status = "FAILED"
                        failed_job.finished_at = datetime.now(UTC)
                        failed_job.error_message = str(exc)[:500]
                        session.commit()
                    raise
            return DataImportResult(job_id, 0, 0, 0)
        return self.run_job(job_id, [symbol], start, end)

    def _is_existing_bar(self, session: Session, bar: RawDailyBar) -> bool:
        exchange, symbol = _split_symbol(bar.symbol)
        instrument_id = session.scalar(
            select(InstrumentModel.id).where(
                InstrumentModel.exchange == exchange,
                InstrumentModel.symbol == symbol,
            )
        )
        if instrument_id is None:
            return False
        timestamp = datetime.combine(bar.trade_date, time.min, tzinfo=UTC)
        return (
            session.scalar(
                select(MarketBarModel.id).where(
                    MarketBarModel.instrument_id == instrument_id,
                    MarketBarModel.timeframe == "1d",
                    MarketBarModel.timestamp == timestamp,
                    MarketBarModel.source == self._provider.name,
                )
            )
            is not None
        )

    def _sync_instrument_metadata(self, session: Session, symbols: list[str]) -> None:
        symbols_needing_metadata: list[str] = []
        for qualified_symbol in symbols:
            exchange, symbol = _split_symbol(qualified_symbol)
            instrument = session.scalar(
                select(InstrumentModel).where(
                    InstrumentModel.exchange == exchange,
                    InstrumentModel.symbol == symbol,
                )
            )
            if instrument is None or instrument.name == symbol:
                symbols_needing_metadata.append(qualified_symbol)
        if not symbols_needing_metadata:
            return

        try:
            raw_instruments = self._provider.fetch_instruments(symbols_needing_metadata)
        except Exception as exc:
            logger.warning("Instrument metadata sync skipped: %s", exc)
            return

        for raw_instrument in raw_instruments:
            instrument = self._get_or_create_instrument(session, raw_instrument.symbol)
            instrument.name = raw_instrument.name
            instrument.board = raw_instrument.board
        session.flush()

    @staticmethod
    def _get_or_create_instrument(session: Session, qualified_symbol: str) -> InstrumentModel:
        exchange, symbol = _split_symbol(qualified_symbol)
        instrument = session.scalar(
            select(InstrumentModel).where(
                InstrumentModel.exchange == exchange,
                InstrumentModel.symbol == symbol,
            )
        )
        if instrument is not None:
            return instrument
        instrument = InstrumentModel(
            exchange=exchange,
            symbol=symbol,
            name=symbol,
            board="UNKNOWN",
            status="ACTIVE",
        )
        session.add(instrument)
        session.flush()
        return instrument


def _split_symbol(qualified_symbol: str) -> tuple[str, str]:
    try:
        exchange, symbol = qualified_symbol.split(":", maxsplit=1)
    except ValueError as exc:
        raise ValueError("INVALID_SYMBOL_FORMAT") from exc
    if exchange not in {"SSE", "SZSE", "BSE"} or not symbol:
        raise ValueError("INVALID_SYMBOL_FORMAT")
    return exchange, symbol
