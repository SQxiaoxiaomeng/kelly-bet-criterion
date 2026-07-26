from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.infrastructure.database import create_session_factory
from app.infrastructure.models import BacktestJobModel, TradingCalendarModel

router = APIRouter(prefix="/operations", tags=["operations"])


class OperationsStatusResponse(BaseModel):
    database: str
    task_execution_mode: str
    market_data_provider: str
    backtest_market_data: str
    latest_calendar_date: date | None
    pending_backtest_job_count: int


@router.get("/status", response_model=OperationsStatusResponse)
def operations_status() -> OperationsStatusResponse:
    try:
        with create_session_factory()() as session:
            session.execute(text("SELECT 1"))
            latest_calendar_date = session.scalar(select(func.max(TradingCalendarModel.trade_date)))
            pending_backtest_job_count = session.scalar(
                select(func.count()).select_from(BacktestJobModel).where(
                    BacktestJobModel.status.in_(("PENDING", "RUNNING"))
                )
            )
        database_status = "available"
    except Exception:
        database_status = "unavailable"
        latest_calendar_date = None
        pending_backtest_job_count = 0
    settings = get_settings()
    return OperationsStatusResponse(
        database=database_status,
        task_execution_mode=settings.task_execution_mode,
        market_data_provider=settings.market_data_provider,
        backtest_market_data=settings.backtest_market_data,
        latest_calendar_date=latest_calendar_date,
        pending_backtest_job_count=pending_backtest_job_count or 0,
    )
