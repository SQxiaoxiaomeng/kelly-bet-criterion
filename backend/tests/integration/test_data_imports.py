from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.routes import data as data_routes
from app.application.corporate_actions import CorporateActionImportService
from app.application.data_imports import DataImportService
from app.application.trading_calendar import TradingCalendarService
from app.core.config import Settings
from app.infrastructure import models  # noqa: F401
from app.infrastructure.database import Base
from app.infrastructure.market_data_reader import SqlAlchemyMarketDataReader
from app.infrastructure.models import (
    CorporateActionModel,
    DataImportJobModel,
    InstrumentModel,
    MarketBarModel,
    TradingCalendarModel,
)
from app.main import create_app
from app.providers.base import RawCashDividend, RawDailyBar, RawInstrument, RawTradingDay
from app.providers.fixture_provider import FixtureMarketDataProvider


class StaticProvider:
    name = "static-test"
    instrument_name = "浦发银行"
    metadata_call_count = 0

    def fetch_instruments(self, symbols: list[str]) -> list[RawInstrument]:
        self.metadata_call_count += 1
        return [
            RawInstrument(symbol=symbol, name=self.instrument_name, board="MAIN")
            for symbol in symbols
        ]

    def fetch_daily_bars(self, symbols: list[str], start: date, end: date) -> list[RawDailyBar]:
        return [
            RawDailyBar(
                symbol="SSE:600000",
                trade_date=date(2026, 7, 24),
                open=Decimal("10.00"),
                high=Decimal("10.50"),
                low=Decimal("9.90"),
                close=Decimal("10.25"),
                volume=Decimal("100000"),
                amount=Decimal("1025000"),
                published_at=datetime(2026, 7, 24, 8, tzinfo=UTC),
            )
        ]

    def fetch_trading_calendar(
        self, exchange: str, start: date, end: date
    ) -> list[RawTradingDay]:
        return [RawTradingDay(exchange=exchange, trade_date=start, is_open=True)]

    def fetch_cash_dividends(
        self, symbols: list[str], start: date, end: date
    ) -> list[RawCashDividend]:
        return []


class StaticDividendProvider(StaticProvider):
    def fetch_cash_dividends(
        self, symbols: list[str], start: date, end: date
    ) -> list[RawCashDividend]:
        return [
            RawCashDividend(
                symbol="SSE:600000",
                ex_date=date(2026, 7, 24),
                cash_per_share=Decimal("0.10"),
                published_at=datetime(2026, 7, 20, tzinfo=UTC),
            )
        ]


class MetadataUnavailableProvider(StaticProvider):
    def fetch_instruments(self, symbols: list[str]) -> list[RawInstrument]:
        raise RuntimeError("METADATA_RATE_LIMITED")


def test_daily_bars_are_append_only_and_job_is_auditable(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'market.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    service = DataImportService(sessions, StaticProvider())

    first_job_id = service.create_job()
    first = service.run_job(first_job_id, ["SSE:600000"], date(2026, 7, 24), date(2026, 7, 24))
    second_job_id = service.create_job()
    second = service.run_job(second_job_id, ["SSE:600000"], date(2026, 7, 24), date(2026, 7, 24))

    assert first.imported_count == 1
    assert second.duplicate_count == 1
    with sessions() as session:
        assert len(list(session.scalars(select(MarketBarModel)))) == 1
        instrument = session.scalar(select(InstrumentModel))
        assert instrument is not None
        assert instrument.name == "浦发银行"
        job = session.get(DataImportJobModel, first_job_id)
        assert job is not None
        assert job.status == "COMPLETED"


def test_reader_returns_only_valid_bars_and_a_content_addressed_snapshot(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'reader.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    service = DataImportService(sessions, StaticProvider())
    job_id = service.create_job()
    service.run_job(job_id, ["SSE:600000"], date(2026, 7, 24), date(2026, 7, 24))

    bars, snapshot_id = SqlAlchemyMarketDataReader(sessions, "static-test").read_daily_bars(
        "SSE:600000", date(2026, 7, 24), date(2026, 7, 24)
    )

    assert len(bars) == 1
    assert bars[0].close == Decimal("10.2500")
    assert snapshot_id.startswith("market-bars:static-test:")


def test_full_history_skips_metadata_lookup_when_name_is_already_cached(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'metadata-refresh.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    provider = StaticProvider()
    service = DataImportService(sessions, provider)

    first_job_id = service.create_job()
    service.run_full_history_job(first_job_id, "SSE:600000", date(2026, 7, 24))
    second_job_id = service.create_job()
    result = service.run_full_history_job(second_job_id, "SSE:600000", date(2026, 7, 24))

    assert result.imported_count == 0
    assert provider.metadata_call_count == 1
    with sessions() as session:
        instrument = session.scalar(select(InstrumentModel))
        assert instrument is not None
        assert instrument.name == "浦发银行"


def test_daily_import_continues_when_instrument_metadata_is_rate_limited(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'metadata-rate-limit.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    service = DataImportService(sessions, MetadataUnavailableProvider())

    job_id = service.create_job()
    result = service.run_job(job_id, ["SSE:600000"], date(2026, 7, 24), date(2026, 7, 24))

    assert result.imported_count == 1
    with sessions() as session:
        instrument = session.scalar(select(InstrumentModel))
        assert instrument is not None
        assert instrument.name == "600000"
        job = session.get(DataImportJobModel, job_id)
        assert job is not None
        assert job.status == "COMPLETED"


def test_local_mode_import_endpoint_runs_without_celery_or_redis(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'local-mode.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'local-mode.db'}",
        market_data_provider="fixture",
        task_execution_mode="local",
    )
    monkeypatch.setattr(data_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(data_routes, "create_session_factory", lambda: sessions)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/data/imports",
        json={
            "symbols": ["SSE:600000"],
            "start": "2026-07-24",
            "end": "2026-07-24",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["task_id"] == "local-1"

    status_response = client.get("/api/v1/data/sync-status")
    assert status_response.status_code == 200
    assert status_response.json()["granularity"] == "1d"
    assert status_response.json()["latest_market_timestamp"] is not None

    availability_response = client.get(
        "/api/v1/data/availability",
        params={"symbol": "SSE:600000", "start": "2026-07-24", "end": "2026-07-24"},
    )
    assert availability_response.status_code == 200
    assert availability_response.json()["is_available"] is True
    assert availability_response.json()["bar_count"] == 1

    instruments_response = client.get("/api/v1/data/instruments")
    assert instruments_response.status_code == 200
    assert instruments_response.json()[0]["symbol"] == "SSE:600000"

    bars_response = client.get("/api/v1/data/daily-bars", params={"symbol": "SSE:600000"})
    assert bars_response.status_code == 200
    assert bars_response.json()[0]["trade_date"] == "2026-07-24"

    delete_response = client.delete("/api/v1/data/instruments/SSE:600000")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_bar_count"] == 1
    assert client.get("/api/v1/data/instruments").json() == []

    full_history_response = client.post(
        "/api/v1/data/imports/full-history", json={"symbol": "600000"}
    )
    assert full_history_response.status_code == 200
    assert full_history_response.json()["symbol"] == "SSE:600000"

    initial_window = client.get(
        "/api/v1/data/daily-bars", params={"symbol": "SSE:600000", "limit": 3}
    )
    shifted_older_window = client.get(
        "/api/v1/data/daily-bars",
        params={"symbol": "SSE:600000", "limit": 3, "end": "2026-07-23"},
    )
    shifted_newer_window = client.get(
        "/api/v1/data/daily-bars",
        params={"symbol": "SSE:600000", "limit": 3, "after": "2026-07-23"},
    )
    assert [bar["trade_date"] for bar in initial_window.json()] == [
        "2026-07-22",
        "2026-07-23",
        "2026-07-24",
    ]
    assert [bar["trade_date"] for bar in shifted_older_window.json()] == [
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
    ]
    assert [bar["trade_date"] for bar in shifted_newer_window.json()] == [
        "2026-07-22",
        "2026-07-23",
        "2026-07-24",
    ]


def test_calendar_sync_makes_sessions_explicit(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'calendar.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    fixture_path = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    service = TradingCalendarService(sessions, FixtureMarketDataProvider(fixture_path))

    result = service.sync("SSE", date(2026, 7, 16), date(2026, 7, 24))

    assert result.imported_count == 7
    assert service.is_open("SSE", date(2026, 7, 24)) is True
    assert service.is_open("SSE", date(2026, 7, 25)) is None
    with sessions() as session:
        assert len(list(session.scalars(select(TradingCalendarModel)))) == 7


def test_full_history_import_starts_from_first_available_provider_bar(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'full-history.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    fixture_path = Path(__file__).parents[1] / "fixtures" / "daily_bars.json"
    service = DataImportService(sessions, FixtureMarketDataProvider(fixture_path))
    job_id = service.create_job()

    result = service.run_full_history_job(job_id, "SSE:600000", date(2026, 7, 31))

    assert result.imported_count == 7


def test_cash_dividend_import_is_append_only(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'dividend-import.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        session.add(
            InstrumentModel(
                exchange="SSE", symbol="600000", name="测试证券", board="MAIN", status="ACTIVE"
            )
        )
        session.commit()
    service = CorporateActionImportService(sessions, StaticDividendProvider())

    first = service.sync_cash_dividends(["SSE:600000"], date(2026, 7, 1), date(2026, 7, 31))
    second = service.sync_cash_dividends(["SSE:600000"], date(2026, 7, 1), date(2026, 7, 31))

    assert first.imported_count == 1
    assert second.duplicate_count == 1
    with sessions() as session:
        assert len(list(session.scalars(select(CorporateActionModel)))) == 1
