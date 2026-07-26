from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api.routes import backtests as backtest_routes
from app.core.config import Settings
from app.main import create_app


def test_backtest_api_runs_fixture_strategy_and_returns_report(monkeypatch: MonkeyPatch) -> None:
    settings = Settings(
        backtest_repository="memory",
        backtest_market_data="fixture",
        market_data_provider="fixture",
    )
    monkeypatch.setattr(backtest_routes, "get_settings", lambda: settings)
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/backtests",
        json={
            "symbol": "SSE:600000",
            "start": "2026-07-16",
            "end": "2026-07-24",
            "initial_cash": "100000",
            "short_window": 3,
            "long_window": 5,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["data_snapshot_id"] == "fixture:daily-bars:v1"
    assert payload["data_source"] == "fixture"
    assert payload["adjustment_mode"] == "none"
    assert payload["fee_model"] == "a_share_default_v1"
    assert payload["equity_curve"]
