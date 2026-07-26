from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.application.backtest_jobs import BacktestJobService
from app.application.backtests import (
    BacktestRequest,
    BacktestService,
    InMemoryBacktestRepository,
    StoredBacktest,
)
from app.core.config import get_settings
from app.infrastructure.backtest_repository import SqlAlchemyBacktestRepository
from app.infrastructure.database import create_session_factory
from app.infrastructure.market_data_reader import SqlAlchemyMarketDataReader
from app.infrastructure.models import BacktestJobModel
from app.workers.backtest_tasks import run_backtest

router = APIRouter(prefix="/backtests", tags=["backtests"])
fixture_path = Path(__file__).parents[3] / "tests" / "fixtures" / "daily_bars.json"
memory_repository = InMemoryBacktestRepository()


def _create_service() -> BacktestService:
    settings = get_settings()
    repository = (
        SqlAlchemyBacktestRepository(create_session_factory())
        if settings.backtest_repository == "sql"
        else memory_repository
    )
    reader = (
        SqlAlchemyMarketDataReader(create_session_factory(), settings.market_data_provider)
        if settings.backtest_market_data == "database"
        else None
    )
    return BacktestService(fixture_path, repository, reader)


class StrategyInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    parameters: dict[str, int]


class CreateBacktestRequest(BaseModel):
    strategy_name: str = "moving_average_cross"
    symbol: str = "SSE:600000"
    start: date = date(2026, 7, 1)
    end: date = date(2026, 7, 31)
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    short_window: int = Field(default=3, gt=0)
    long_window: int = Field(default=5, gt=0)
    grid_step_percent: Decimal = Field(default=Decimal("0.05"), gt=0, lt=Decimal("0.50"))


class TradeResponse(BaseModel):
    trade_date: date
    side: str
    price: Decimal
    quantity: int
    fee: Decimal


class EquityPointResponse(BaseModel):
    trade_date: date
    equity: Decimal


class ReplayDailyBarResponse(BaseModel):
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class MetricsResponse(BaseModel):
    total_return: Decimal
    max_drawdown: Decimal
    volatility: Decimal
    trade_count: int
    total_fees: Decimal
    annualized_sharpe: Decimal
    turnover: Decimal


class BacktestResponse(BaseModel):
    id: UUID
    status: str = "completed"
    strategy: str
    strategy_version: str
    data_snapshot_id: str
    data_source: str
    adjustment_mode: str = "none"
    fee_model: str = "a_share_default_v1"
    metrics: MetricsResponse
    trades: list[TradeResponse]
    equity_curve: list[EquityPointResponse]
    data_granularity: str = "1d"
    execution_assumption: str = "signal_at_close_execute_next_open"
    symbol: str
    start: date
    end: date
    daily_bars: list[ReplayDailyBarResponse]


class BacktestJobResponse(BaseModel):
    id: UUID
    status: str
    run_id: UUID | None
    error_message: str | None


class BacktestJobHistoryResponse(BacktestJobResponse):
    symbol: str
    start: date
    end: date
    strategy_name: str
    initial_cash: Decimal
    short_window: int
    long_window: int
    created_at: datetime
    finished_at: datetime | None


@router.get("/strategies", response_model=list[StrategyInfoResponse])
def list_strategies() -> list[StrategyInfoResponse]:
    service = _create_service()
    return [StrategyInfoResponse.model_validate(item) for item in service.list_strategies()]


@router.post("", response_model=BacktestResponse, status_code=status.HTTP_201_CREATED)
def create_backtest(payload: CreateBacktestRequest) -> BacktestResponse:
    service = _create_service()
    try:
        run = service.create_moving_average_run(
            BacktestRequest(
                symbol=payload.symbol,
                start=payload.start,
                end=payload.end,
                initial_cash=payload.initial_cash,
                short_window=payload.short_window,
                long_window=payload.long_window,
                strategy_name=payload.strategy_name,
                grid_step_percent=payload.grid_step_percent,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_response(run)


@router.post("/jobs", response_model=BacktestJobResponse, status_code=status.HTTP_201_CREATED)
def create_backtest_job(payload: CreateBacktestRequest) -> BacktestJobResponse:
    settings = get_settings()
    request = BacktestRequest(
        symbol=payload.symbol,
        start=payload.start,
        end=payload.end,
        initial_cash=payload.initial_cash,
        short_window=payload.short_window,
        long_window=payload.long_window,
        strategy_name=payload.strategy_name,
        grid_step_percent=payload.grid_step_percent,
    )
    job_service = BacktestJobService(create_session_factory())
    job_id = job_service.create(request)
    if settings.task_execution_mode == "local":
        try:
            job_service.execute(job_id, _create_service())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
    elif settings.task_execution_mode == "celery":
        run_backtest.delay(str(job_id))
    else:
        raise HTTPException(status_code=422, detail="UNSUPPORTED_TASK_EXECUTION_MODE")
    job = job_service.get(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="BACKTEST_JOB_NOT_FOUND_AFTER_EXECUTION")
    return _to_job_response(job)


@router.get("/jobs/{job_id}", response_model=BacktestJobResponse)
def get_backtest_job(job_id: UUID) -> BacktestJobResponse:
    job = BacktestJobService(create_session_factory()).get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BACKTEST_JOB_NOT_FOUND")
    return _to_job_response(job)


@router.get("/jobs", response_model=list[BacktestJobHistoryResponse])
def list_backtest_jobs(
    limit: int = Query(default=50, ge=1, le=100),
) -> list[BacktestJobHistoryResponse]:
    jobs = BacktestJobService(create_session_factory()).list(limit)
    return [_to_job_history_response(job) for job in jobs]


@router.post("/jobs/{job_id}/cancel", response_model=BacktestJobResponse)
def cancel_backtest_job(job_id: UUID) -> BacktestJobResponse:
    try:
        job = BacktestJobService(create_session_factory()).cancel(job_id)
    except ValueError as exc:
        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc) == "BACKTEST_JOB_NOT_FOUND"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=error_status, detail=str(exc)) from exc
    return _to_job_response(job)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backtest_job(job_id: UUID) -> Response:
    try:
        BacktestJobService(create_session_factory()).delete(job_id)
    except ValueError as exc:
        error_status = (
            status.HTTP_404_NOT_FOUND
            if str(exc) == "BACKTEST_JOB_NOT_FOUND"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=error_status, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{run_id}", response_model=BacktestResponse)
def get_backtest(run_id: UUID) -> BacktestResponse:
    service = _create_service()
    run = service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BACKTEST_NOT_FOUND")
    return _to_response(run)


def _to_response(run: StoredBacktest) -> BacktestResponse:
    return BacktestResponse(
        id=run.id,
        strategy=run.strategy_name,
        strategy_version=run.strategy_version,
        data_snapshot_id=run.data_snapshot_id,
        data_source=run.data_snapshot_id.split(":", maxsplit=1)[0],
        metrics=MetricsResponse.model_validate(run.result.metrics, from_attributes=True),
        trades=[
            TradeResponse.model_validate(trade, from_attributes=True) for trade in run.result.trades
        ],
        equity_curve=[
            EquityPointResponse.model_validate(point, from_attributes=True)
            for point in run.result.equity_curve
        ],
        symbol=run.request.symbol,
        start=run.request.start,
        end=run.request.end,
        daily_bars=[
            ReplayDailyBarResponse(
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in run.daily_bars
        ],
    )


def _to_job_response(job: BacktestJobModel) -> BacktestJobResponse:
    return BacktestJobResponse(
        id=UUID(job.id),
        status=job.status,
        run_id=UUID(job.run_id) if job.run_id is not None else None,
        error_message=job.error_message,
    )


def _to_job_history_response(job: BacktestJobModel) -> BacktestJobHistoryResponse:
    request = job.request
    return BacktestJobHistoryResponse(
        **_to_job_response(job).model_dump(),
        symbol=str(request["symbol"]),
        start=date.fromisoformat(str(request["start"])),
        end=date.fromisoformat(str(request["end"])),
        strategy_name=str(request["strategy_name"]),
        initial_cash=Decimal(str(request["initial_cash"])),
        short_window=int(request["short_window"]),
        long_window=int(request["long_window"]),
        created_at=job.created_at,
        finished_at=job.finished_at,
    )
