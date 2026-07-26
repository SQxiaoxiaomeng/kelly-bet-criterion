from uuid import UUID

from app.application.backtest_jobs import BacktestJobService
from app.core.config import get_settings
from app.infrastructure.backtest_service_factory import create_backtest_service
from app.infrastructure.database import create_session_factory
from app.workers.celery_app import celery_app


@celery_app.task(name="backtests.run")  # type: ignore[untyped-decorator]
def run_backtest(job_id: str) -> dict[str, str]:
    settings = get_settings()
    service = BacktestJobService(create_session_factory())
    run_id = service.execute(UUID(job_id), create_backtest_service(settings))
    return {"job_id": job_id, "run_id": str(run_id)}
