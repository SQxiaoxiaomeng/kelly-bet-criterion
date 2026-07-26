from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.backtests import BacktestRequest, BacktestService
from app.infrastructure import models  # noqa: F401
from app.infrastructure.backtest_repository import SqlAlchemyBacktestRepository
from app.infrastructure.database import Base


def test_sql_repository_persists_completed_backtest(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'backtests.db'}")
    Base.metadata.create_all(engine)
    repository = SqlAlchemyBacktestRepository(sessionmaker(bind=engine))
    fixture = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    service = BacktestService(fixture, repository)

    created = service.create_moving_average_run(
        BacktestRequest(
            symbol="SSE:600000",
            start=date(2026, 7, 16),
            end=date(2026, 7, 24),
            initial_cash=Decimal("100000"),
            short_window=3,
            long_window=5,
        )
    )

    loaded = repository.get(created.id)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.request == created.request
    assert loaded.daily_bars == created.daily_bars
    assert loaded.result.metrics == created.result.metrics
