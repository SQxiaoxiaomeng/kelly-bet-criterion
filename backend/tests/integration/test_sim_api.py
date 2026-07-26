from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes import sim
from app.application.paper_trading import PaperTradingService
from app.infrastructure import models  # noqa: F401
from app.infrastructure.database import Base
from app.infrastructure.models import InstrumentModel, MarketBarModel
from app.main import create_app


def test_sim_api_creates_account_and_applies_t_plus_one(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'sim-api.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        instrument = InstrumentModel(
            exchange="SSE", symbol="600000", name="测试证券", board="MAIN", status="ACTIVE"
        )
        session.add(instrument)
        session.flush()
        session.add(
            MarketBarModel(
                instrument_id=instrument.id,
                timeframe="1d",
                timestamp=datetime(2026, 7, 24, tzinfo=UTC),
                open=Decimal("10"),
                high=Decimal("10.5"),
                low=Decimal("9.5"),
                close=Decimal("10"),
                volume=Decimal("100000"),
                amount=None,
                source="fixture",
                observed_at=datetime.now(UTC),
                published_at=datetime.now(UTC),
                quality_status="VALID",
            )
        )
        session.commit()
    monkeypatch.setattr(sim, "_service", lambda: PaperTradingService(sessions, "fixture"))
    client = TestClient(create_app())

    account_response = client.post(
        "/api/v1/sim/accounts", json={"name": "测试账户", "initial_cash": "10000"}
    )
    account_id = account_response.json()["id"]
    accounts_response = client.get("/api/v1/sim/accounts")
    with client.websocket_connect(f"/api/v1/sim/accounts/{account_id}/stream") as websocket:
        initial_state = websocket.receive_json()
    dividend_response = client.post(
        "/api/v1/sim/corporate-actions/cash-dividends",
        json={"symbol": "SSE:600000", "ex_date": "2026-07-24", "cash_per_share": "0.10"},
    )
    buy_response = client.post(
        f"/api/v1/sim/accounts/{account_id}/orders",
        headers={"Idempotency-Key": "api-buy-001"},
        json={"symbol": "SSE:600000", "side": "BUY", "quantity": 100, "limit_price": "10"},
    )
    sell_response = client.post(
        f"/api/v1/sim/accounts/{account_id}/orders",
        headers={"Idempotency-Key": "api-sell-001"},
        json={"symbol": "SSE:600000", "side": "SELL", "quantity": 100, "limit_price": "10"},
    )
    fills_response = client.get(f"/api/v1/sim/accounts/{account_id}/fills")
    ledger_response = client.get(f"/api/v1/sim/accounts/{account_id}/cash-ledger")

    assert account_response.status_code == 201
    assert accounts_response.status_code == 200
    assert accounts_response.json()[0]["id"] == account_id
    assert accounts_response.json()[0]["created_at"]
    assert initial_state["type"] == "account_state"
    assert initial_state["account"]["id"] == account_id
    assert dividend_response.status_code == 200
    assert dividend_response.json()["action_type"] == "CASH_DIVIDEND"
    assert buy_response.json()["status"] == "FILLED"
    assert sell_response.json()["status"] == "REJECTED"
    assert sell_response.json()["rejection_reason"] == "INSUFFICIENT_SETTLED_QUANTITY"
    assert fills_response.status_code == 200
    assert fills_response.json()[0]["quantity"] == 100
    assert ledger_response.status_code == 200
    assert {entry["reason"] for entry in ledger_response.json()} == {
        "INITIAL_DEPOSIT",
        "ORDER_FILL",
    }
    rename_response = client.patch(
        f"/api/v1/sim/accounts/{account_id}", json={"name": "已重命名账户"}
    )
    archive_response = client.patch(
        f"/api/v1/sim/accounts/{account_id}", json={"status": "ARCHIVED"}
    )
    empty_account_response = client.post(
        "/api/v1/sim/accounts", json={"name": "空账户", "initial_cash": "10000"}
    )
    empty_account_id = empty_account_response.json()["id"]
    delete_empty_response = client.delete(f"/api/v1/sim/accounts/{empty_account_id}")
    delete_history_response = client.delete(f"/api/v1/sim/accounts/{account_id}")

    assert rename_response.json()["name"] == "已重命名账户"
    assert archive_response.json()["status"] == "ARCHIVED"
    assert delete_empty_response.status_code == 204
    assert delete_history_response.status_code == 409
