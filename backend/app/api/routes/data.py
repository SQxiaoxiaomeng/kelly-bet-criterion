from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.application.corporate_actions import CorporateActionImportService
from app.application.data_imports import DataImportService
from app.application.trading_calendar import TradingCalendarService
from app.core.config import get_settings
from app.infrastructure.database import create_session_factory
from app.infrastructure.models import DataImportJobModel, InstrumentModel, MarketBarModel
from app.providers.factory import create_market_data_provider
from app.workers.data_import_tasks import run_daily_bar_import

router = APIRouter(prefix="/data", tags=["data"])


class DataStatusResponse(BaseModel):
    status: str
    source: str | None
    message: str
    latest_market_timestamp: datetime | None
    latest_observed_at: datetime | None
    granularity: str = "1d"


class DataAvailabilityResponse(BaseModel):
    symbol: str
    start: date
    end: date
    bar_count: int
    is_available: bool


class FullHistoryImportRequest(BaseModel):
    symbol: str


class ImportedInstrumentResponse(BaseModel):
    symbol: str
    name: str
    board: str
    bar_count: int
    latest_trade_date: date


class DailyBarResponse(BaseModel):
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class DeleteImportedDataResponse(BaseModel):
    symbol: str
    deleted_bar_count: int


class CreateDataImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=100)
    start: date
    end: date


class DataImportAcceptedResponse(BaseModel):
    job_id: int
    task_id: str
    status: str
    symbol: str | None = None


class DataImportJobResponse(BaseModel):
    job_id: int
    provider: str
    dataset: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class CalendarSyncRequest(BaseModel):
    exchange: str = Field(pattern="^(SSE|SZSE)$")
    start: date
    end: date


class CalendarSyncResponse(BaseModel):
    exchange: str
    imported_count: int
    updated_count: int


class CorporateActionImportRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=100)
    start: date
    end: date


class CorporateActionImportResponse(BaseModel):
    imported_count: int
    duplicate_count: int


@router.get("/sync-status", response_model=DataStatusResponse)
def data_sync_status() -> DataStatusResponse:
    settings = get_settings()
    is_local = settings.task_execution_mode == "local"
    with create_session_factory()() as session:
        latest_bar = session.scalar(
            select(MarketBarModel)
            .where(
                MarketBarModel.source == settings.market_data_provider,
                MarketBarModel.timeframe == "1d",
            )
            .order_by(MarketBarModel.timestamp.desc(), MarketBarModel.observed_at.desc())
        )
    return DataStatusResponse(
        status="configured",
        source=settings.market_data_provider,
        message=(
            "本地同步模式已启用，导入请求将在 API 进程内执行。"
            if is_local
            else "行情导入任务将由后台 Worker 异步执行。"
        ),
        latest_market_timestamp=latest_bar.timestamp if latest_bar is not None else None,
        latest_observed_at=latest_bar.observed_at if latest_bar is not None else None,
    )


@router.get("/availability", response_model=DataAvailabilityResponse)
def data_availability(symbol: str, start: date, end: date) -> DataAvailabilityResponse:
    if start > end:
        raise HTTPException(status_code=422, detail="INVALID_DATE_RANGE")
    try:
        exchange, code = symbol.split(":", maxsplit=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_SYMBOL_FORMAT") from exc
    settings = get_settings()
    with create_session_factory()() as session:
        bar_count = session.scalar(
            select(func.count())
            .select_from(MarketBarModel)
            .join(InstrumentModel, MarketBarModel.instrument_id == InstrumentModel.id)
            .where(
                MarketBarModel.timeframe == "1d",
                MarketBarModel.source == settings.market_data_provider,
                MarketBarModel.quality_status == "VALID",
                MarketBarModel.timestamp >= datetime.combine(start, datetime.min.time(), UTC),
                MarketBarModel.timestamp <= datetime.combine(end, datetime.max.time(), UTC),
                InstrumentModel.exchange == exchange,
                InstrumentModel.symbol == code,
            )
        )
    return DataAvailabilityResponse(
        symbol=symbol,
        start=start,
        end=end,
        bar_count=bar_count or 0,
        is_available=(bar_count or 0) > 0,
    )


@router.post(
    "/imports",
    response_model=DataImportAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_data_import(request: CreateDataImportRequest) -> DataImportAcceptedResponse:
    if request.start > request.end:
        raise HTTPException(status_code=422, detail="INVALID_DATE_RANGE")
    settings = get_settings()
    service = DataImportService(
        create_session_factory(),
        create_market_data_provider(settings),
    )
    job_id = service.create_job()
    if settings.task_execution_mode == "local":
        service.run_job(job_id, request.symbols, request.start, request.end)
        return DataImportAcceptedResponse(
            job_id=job_id,
            task_id=f"local-{job_id}",
            status="COMPLETED",
        )
    if settings.task_execution_mode != "celery":
        raise HTTPException(status_code=422, detail="UNSUPPORTED_TASK_EXECUTION_MODE")
    task = run_daily_bar_import.delay(
        job_id,
        request.symbols,
        request.start.isoformat(),
        request.end.isoformat(),
    )
    return DataImportAcceptedResponse(job_id=job_id, task_id=task.id, status="PENDING")


@router.post("/imports/full-history", response_model=DataImportAcceptedResponse)
def import_full_history(request: FullHistoryImportRequest) -> DataImportAcceptedResponse:
    settings = get_settings()
    service = DataImportService(create_session_factory(), create_market_data_provider(settings))
    job_id = service.create_job()
    symbol = _normalize_a_share_symbol(request.symbol)
    if settings.task_execution_mode != "local":
        raise HTTPException(status_code=422, detail="FULL_HISTORY_IMPORT_REQUIRES_LOCAL_MODE")
    result = service.run_full_history_job(job_id, symbol, datetime.now(UTC).date())
    return DataImportAcceptedResponse(
        job_id=result.job_id,
        task_id=f"local-{result.job_id}",
        status="COMPLETED",
        symbol=symbol,
    )


@router.get("/instruments", response_model=list[ImportedInstrumentResponse])
def list_imported_instruments() -> list[ImportedInstrumentResponse]:
    settings = get_settings()
    with create_session_factory()() as session:
        rows = session.execute(
            select(
                InstrumentModel.exchange,
                InstrumentModel.symbol,
                InstrumentModel.name,
                InstrumentModel.board,
                func.count(MarketBarModel.id),
                func.max(MarketBarModel.timestamp),
            )
            .join(MarketBarModel, MarketBarModel.instrument_id == InstrumentModel.id)
            .where(
                MarketBarModel.source == settings.market_data_provider,
                MarketBarModel.timeframe == "1d",
                MarketBarModel.quality_status == "VALID",
            )
            .group_by(InstrumentModel.id)
            .order_by(InstrumentModel.exchange, InstrumentModel.symbol)
        )
        return [
            ImportedInstrumentResponse(
                symbol=f"{exchange}:{symbol}",
                name=name,
                board=board,
                bar_count=count,
                latest_trade_date=latest.date(),
            )
            for exchange, symbol, name, board, count, latest in rows
            if latest is not None
        ]


@router.get("/daily-bars", response_model=list[DailyBarResponse])
def list_daily_bars(
    symbol: str,
    limit: int = Query(default=240, ge=1, le=2000),
    end: date | None = Query(default=None),
    after: date | None = Query(default=None),
) -> list[DailyBarResponse]:
    if end is not None and after is not None:
        raise HTTPException(status_code=422, detail="END_AND_AFTER_ARE_MUTUALLY_EXCLUSIVE")
    try:
        exchange, code = symbol.split(":", maxsplit=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_SYMBOL_FORMAT") from exc
    settings = get_settings()
    with create_session_factory()() as session:
        filters = [
            InstrumentModel.exchange == exchange,
            InstrumentModel.symbol == code,
            MarketBarModel.source == settings.market_data_provider,
            MarketBarModel.timeframe == "1d",
            MarketBarModel.quality_status == "VALID",
        ]
        if after is not None:
            next_timestamp = session.scalar(
                select(MarketBarModel.timestamp)
                .join(InstrumentModel, MarketBarModel.instrument_id == InstrumentModel.id)
                .where(
                    *filters,
                    MarketBarModel.timestamp > datetime.combine(after, datetime.max.time(), UTC),
                )
                .order_by(MarketBarModel.timestamp.asc())
            )
            if next_timestamp is None:
                return []
            end = next_timestamp.date()
        query = (
            select(MarketBarModel)
            .join(InstrumentModel, MarketBarModel.instrument_id == InstrumentModel.id)
            .where(*filters)
            .order_by(MarketBarModel.timestamp.desc())
            .limit(limit)
        )
        if end is not None:
            query = query.where(
                MarketBarModel.timestamp <= datetime.combine(end, datetime.max.time(), UTC)
            )
        bars = list(
            session.scalars(
                query
            )
        )
    return [
        DailyBarResponse(
            trade_date=bar.timestamp.date(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )
        for bar in reversed(bars)
    ]


@router.delete("/instruments/{symbol:path}", response_model=DeleteImportedDataResponse)
def delete_imported_instrument_data(symbol: str) -> DeleteImportedDataResponse:
    try:
        exchange, code = symbol.split(":", maxsplit=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="INVALID_SYMBOL_FORMAT") from exc
    settings = get_settings()
    with create_session_factory()() as session:
        instrument = session.scalar(
            select(InstrumentModel).where(
                InstrumentModel.exchange == exchange, InstrumentModel.symbol == code
            )
        )
        if instrument is None:
            raise HTTPException(status_code=404, detail="INSTRUMENT_NOT_FOUND")
        bars = list(
            session.scalars(
                select(MarketBarModel).where(
                    MarketBarModel.instrument_id == instrument.id,
                    MarketBarModel.source == settings.market_data_provider,
                    MarketBarModel.timeframe == "1d",
                )
            )
        )
        for bar in bars:
            session.delete(bar)
        session.commit()
    return DeleteImportedDataResponse(symbol=symbol, deleted_bar_count=len(bars))


def _normalize_a_share_symbol(value: str) -> str:
    normalized = value.strip().upper()
    if ":" in normalized:
        exchange, code = normalized.split(":", maxsplit=1)
        if exchange in {"SSE", "SZSE"} and code.isdigit() and len(code) == 6:
            return normalized
        raise HTTPException(status_code=422, detail="INVALID_SYMBOL_FORMAT")
    if not normalized.isdigit() or len(normalized) != 6:
        raise HTTPException(status_code=422, detail="INVALID_STOCK_CODE")
    if normalized.startswith(("5", "6", "9")):
        return f"SSE:{normalized}"
    if normalized.startswith(("0", "2", "3")):
        return f"SZSE:{normalized}"
    raise HTTPException(status_code=422, detail="UNSUPPORTED_STOCK_CODE")


@router.get("/imports/{job_id}", response_model=DataImportJobResponse)
def get_data_import(job_id: int) -> DataImportJobResponse:
    with create_session_factory()() as session:
        job = session.get(DataImportJobModel, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="DATA_IMPORT_JOB_NOT_FOUND")
        return DataImportJobResponse(
            job_id=job.id,
            provider=job.provider,
            dataset=job.dataset,
            status=job.status,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error_message=job.error_message,
        )


@router.post("/calendars/sync", response_model=CalendarSyncResponse)
def sync_trading_calendar(request: CalendarSyncRequest) -> CalendarSyncResponse:
    if request.start > request.end:
        raise HTTPException(status_code=422, detail="INVALID_DATE_RANGE")
    settings = get_settings()
    try:
        result = TradingCalendarService(
            create_session_factory(), create_market_data_provider(settings)
        ).sync(request.exchange, request.start, request.end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CalendarSyncResponse(
        exchange=request.exchange,
        imported_count=result.imported_count,
        updated_count=result.updated_count,
    )


@router.post("/corporate-actions/cash-dividends/sync", response_model=CorporateActionImportResponse)
def sync_cash_dividends(request: CorporateActionImportRequest) -> CorporateActionImportResponse:
    settings = get_settings()
    try:
        result = CorporateActionImportService(
            create_session_factory(), create_market_data_provider(settings)
        ).sync_cash_dividends(request.symbols, request.start, request.end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CorporateActionImportResponse(
        imported_count=result.imported_count,
        duplicate_count=result.duplicate_count,
    )
