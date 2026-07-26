from datetime import date

from app.application.data_imports import DataImportService
from app.core.config import get_settings
from app.infrastructure.database import create_session_factory
from app.providers.factory import create_market_data_provider
from app.workers.celery_app import celery_app


@celery_app.task(name="data_imports.run_daily_bar_import")  # type: ignore[untyped-decorator]
def run_daily_bar_import(job_id: int, symbols: list[str], start: str, end: str) -> dict[str, int]:
    settings = get_settings()
    service = DataImportService(
        create_session_factory(),
        create_market_data_provider(settings),
    )
    result = service.run_job(job_id, symbols, date.fromisoformat(start), date.fromisoformat(end))
    return {
        "job_id": result.job_id,
        "imported_count": result.imported_count,
        "duplicate_count": result.duplicate_count,
        "invalid_count": result.invalid_count,
    }
