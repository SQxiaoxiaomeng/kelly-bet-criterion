from pathlib import Path

from app.application.backtests import BacktestService, InMemoryBacktestRepository
from app.core.config import Settings
from app.infrastructure.backtest_repository import SqlAlchemyBacktestRepository
from app.infrastructure.database import create_session_factory
from app.infrastructure.market_data_reader import SqlAlchemyMarketDataReader


def create_backtest_service(settings: Settings) -> BacktestService:
    fixture_path = Path(__file__).parents[2] / "tests" / "fixtures" / "daily_bars.json"
    repository = (
        SqlAlchemyBacktestRepository(create_session_factory())
        if settings.backtest_repository == "sql"
        else InMemoryBacktestRepository()
    )
    reader = (
        SqlAlchemyMarketDataReader(create_session_factory(), settings.market_data_provider)
        if settings.backtest_market_data == "database"
        else None
    )
    return BacktestService(fixture_path, repository, reader)
