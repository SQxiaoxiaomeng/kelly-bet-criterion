from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.application.backtests import BacktestRequest, BacktestService
from app.infrastructure.models import BacktestJobModel


class BacktestJobService:
    """Persists a run request before execution so clients can recover task state."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, request: BacktestRequest) -> UUID:
        job_id = uuid4()
        with self._session_factory() as session:
            session.add(
                BacktestJobModel(
                    id=str(job_id),
                    status="PENDING",
                    request={
                        "symbol": request.symbol,
                        "start": request.start.isoformat(),
                        "end": request.end.isoformat(),
                        "initial_cash": str(request.initial_cash),
                        "short_window": request.short_window,
                        "long_window": request.long_window,
                        "strategy_name": request.strategy_name,
                        "grid_step_percent": str(request.grid_step_percent),
                    },
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
        return job_id

    def execute(self, job_id: UUID, backtest_service: BacktestService) -> UUID:
        with self._session_factory() as session:
            job = session.get(BacktestJobModel, str(job_id))
            if job is None:
                raise ValueError("BACKTEST_JOB_NOT_FOUND")
            if job.status != "PENDING":
                raise ValueError("BACKTEST_JOB_NOT_PENDING")
            job.status = "RUNNING"
            job.started_at = datetime.now(UTC)
            session.commit()
            try:
                request = _deserialize_request(job.request)
                run = backtest_service.create_moving_average_run(request)
                job.status = "COMPLETED"
                job.run_id = str(run.id)
                job.finished_at = datetime.now(UTC)
                session.commit()
                return run.id
            except Exception as exc:
                session.rollback()
                failed_job = session.get(BacktestJobModel, str(job_id))
                if failed_job is not None:
                    failed_job.status = "FAILED"
                    failed_job.error_message = str(exc)[:500]
                    failed_job.finished_at = datetime.now(UTC)
                    session.commit()
                raise

    def get(self, job_id: UUID) -> BacktestJobModel | None:
        with self._session_factory() as session:
            return session.get(BacktestJobModel, str(job_id))

    def list(self, limit: int = 50) -> list[BacktestJobModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(BacktestJobModel)
                    .order_by(BacktestJobModel.created_at.desc())
                    .limit(limit)
                )
            )

    def cancel(self, job_id: UUID) -> BacktestJobModel:
        with self._session_factory() as session:
            job = session.get(BacktestJobModel, str(job_id))
            if job is None:
                raise ValueError("BACKTEST_JOB_NOT_FOUND")
            if job.status != "PENDING":
                raise ValueError("BACKTEST_JOB_NOT_CANCELLABLE")
            job.status = "CANCELLED"
            job.finished_at = datetime.now(UTC)
            session.commit()
            return job

    def delete(self, job_id: UUID) -> None:
        with self._session_factory() as session:
            job = session.get(BacktestJobModel, str(job_id))
            if job is None:
                raise ValueError("BACKTEST_JOB_NOT_FOUND")
            if job.status in {"PENDING", "RUNNING"}:
                raise ValueError("BACKTEST_JOB_NOT_DELETABLE")
            session.delete(job)
            session.commit()


def _deserialize_request(payload: dict[str, str | int]) -> BacktestRequest:
    from datetime import date
    from decimal import Decimal

    return BacktestRequest(
        symbol=str(payload["symbol"]),
        start=date.fromisoformat(str(payload["start"])),
        end=date.fromisoformat(str(payload["end"])),
        initial_cash=Decimal(str(payload["initial_cash"])),
        short_window=int(payload["short_window"]),
        long_window=int(payload["long_window"]),
        strategy_name=str(payload["strategy_name"]),
        grid_step_percent=Decimal(str(payload.get("grid_step_percent", "0.05"))),
    )
