from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import backtests as backtest_routes
from app.application.backtest_jobs import BacktestJobService
from app.application.backtests import BacktestRequest, BacktestService
from app.core.config import Settings
from app.infrastructure import models  # noqa: F401
from app.infrastructure.database import Base
from app.main import create_app


def test_local_backtest_job_persists_completion_and_run_id(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    fixture = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    job_service = BacktestJobService(sessions)
    request = BacktestRequest(
        symbol="SSE:600000",
        start=date(2026, 7, 16),
        end=date(2026, 7, 24),
        initial_cash=Decimal("100000"),
        short_window=3,
        long_window=5,
    )

    job_id = job_service.create(request)
    run_id = job_service.execute(job_id, BacktestService(fixture))
    job = job_service.get(job_id)

    assert job is not None
    assert job.status == "COMPLETED"
    assert job.run_id == str(run_id)


def test_lists_newest_jobs_and_deletes_only_completed_jobs(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'history.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    fixture = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    job_service = BacktestJobService(sessions)
    request = BacktestRequest(
        symbol="SSE:600000",
        start=date(2026, 7, 16),
        end=date(2026, 7, 24),
        initial_cash=Decimal("100000"),
        short_window=3,
        long_window=5,
    )

    pending_job_id = job_service.create(request)
    completed_job_id = job_service.create(request)
    job_service.execute(completed_job_id, BacktestService(fixture))

    history = job_service.list()
    assert [job.id for job in history] == [str(completed_job_id), str(pending_job_id)]

    job_service.delete(completed_job_id)
    assert job_service.get(completed_job_id) is None
    try:
        job_service.delete(pending_job_id)
    except ValueError as exc:
        assert str(exc) == "BACKTEST_JOB_NOT_DELETABLE"
    else:
        raise AssertionError("pending backtest jobs must not be deleted")


def test_backtest_history_api_lists_and_deletes_completed_jobs(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'history-api.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    fixture = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'history-api.db'}")
    monkeypatch.setattr(backtest_routes, "create_session_factory", lambda: sessions)
    monkeypatch.setattr(backtest_routes, "get_settings", lambda: settings)
    service = BacktestJobService(sessions)
    request = BacktestRequest(
        symbol="SSE:600000",
        start=date(2026, 7, 16),
        end=date(2026, 7, 24),
        initial_cash=Decimal("100000"),
        short_window=3,
        long_window=5,
    )
    pending_job_id = service.create(request)
    completed_job_id = service.create(request)
    service.execute(completed_job_id, BacktestService(fixture))
    client = TestClient(create_app())

    history_response = client.get("/api/v1/backtests/jobs")
    assert history_response.status_code == 200
    assert {item["id"] for item in history_response.json()} == {
        str(pending_job_id),
        str(completed_job_id),
    }
    assert client.delete(f"/api/v1/backtests/jobs/{pending_job_id}").status_code == 409
    assert client.delete(f"/api/v1/backtests/jobs/{completed_job_id}").status_code == 204
