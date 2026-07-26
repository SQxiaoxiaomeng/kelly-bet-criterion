from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api.routes import data as data_routes
from app.core.config import Settings
from app.main import create_app


def test_health_check_returns_service_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "a-share-quant-lab"


def test_data_status_exposes_configured_provider_state(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        data_routes,
        "get_settings",
        lambda: Settings(market_data_provider="fixture", task_execution_mode="celery"),
    )
    client = TestClient(create_app())

    response = client.get("/api/v1/data/sync-status")

    assert response.status_code == 200
    assert response.json()["status"] == "configured"
    assert response.json()["source"] == "fixture"
