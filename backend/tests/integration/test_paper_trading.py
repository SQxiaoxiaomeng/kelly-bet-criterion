from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.application.paper_trading import (
    CreateAccountCommand,
    PaperTradingService,
    SubmitOrderCommand,
)
from app.infrastructure import models  # noqa: F401
from app.infrastructure.database import Base
from app.infrastructure.models import (
    AccountSnapshotModel,
    AuditEventModel,
    CashLedgerModel,
    CorporateActionModel,
    InstrumentModel,
    MarketBarModel,
    PositionLotModel,
    SimFillModel,
)


def test_buy_is_idempotent_and_same_day_sell_is_rejected(tmp_path: Path) -> None:
    database_path = tmp_path / "paper.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        instrument = InstrumentModel(
            exchange="SSE", symbol="600000", name="浦发银行", board="MAIN", status="ACTIVE"
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
    service = PaperTradingService(sessions, "fixture")
    account = service.create_account(CreateAccountCommand("测试账户", Decimal("10000")))
    buy = SubmitOrderCommand(account.id, "SSE:600000", "BUY", 100, Decimal("10"), "buy-001")

    first = service.submit_order(buy)
    repeated = service.submit_order(buy)
    same_day_sell = service.submit_order(
        SubmitOrderCommand(account.id, "SSE:600000", "SELL", 100, Decimal("10"), "sell-001")
    )

    assert first.status == "FILLED"
    assert repeated.id == first.id
    assert same_day_sell.status == "REJECTED"
    assert same_day_sell.rejection_reason == "INSUFFICIENT_SETTLED_QUANTITY"
    positions = service.list_positions(account.id)
    assert positions[0].quantity == 100
    assert positions[0].available_quantity == 0
    with sessions() as session:
        assert len(list(session.scalars(select(SimFillModel)))) == 1
        assert len(list(session.scalars(select(CashLedgerModel)))) == 2
        assert len(list(session.scalars(select(AuditEventModel)))) >= 3


def test_unfilled_buy_order_releases_cash_when_cancelled(tmp_path: Path) -> None:
    database_path = tmp_path / "cancel-order.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        instrument = InstrumentModel(
            exchange="SSE", symbol="600000", name="浦发银行", board="MAIN", status="ACTIVE"
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
    service = PaperTradingService(sessions, "fixture")
    account = service.create_account(CreateAccountCommand("测试账户", Decimal("10000")))
    order = service.submit_order(
        SubmitOrderCommand(account.id, "SSE:600000", "BUY", 100, Decimal("9"), "pending-buy")
    )

    cancelled = service.cancel_order(account.id, order.id)
    restored_account = service.get_account(account.id)

    assert order.status == "ACCEPTED"
    assert cancelled.status == "CANCELLED"
    assert restored_account is not None
    assert restored_account.cash == Decimal("10000.00")
    assert restored_account.frozen_cash == Decimal("0.00")

    pending_for_settlement = service.submit_order(
        SubmitOrderCommand(account.id, "SSE:600000", "BUY", 100, Decimal("9"), "settle-buy")
    )
    settlement = service.settle_end_of_day(account.id)

    assert pending_for_settlement.status == "ACCEPTED"
    assert settlement.expired_order_count == 1
    settled_account = service.get_account(account.id)
    assert settled_account is not None
    assert settled_account.cash == Decimal("10000.00")

    with sessions() as session:
        snapshot = session.scalar(select(AccountSnapshotModel))
        assert snapshot is not None
        assert snapshot.equity == Decimal("10000.00")


def test_risk_event_is_recorded_for_order_notional_limit(tmp_path: Path) -> None:
    database_path = tmp_path / "risk.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        instrument = InstrumentModel(
            exchange="SSE", symbol="600000", name="浦发银行", board="MAIN", status="ACTIVE"
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
    service = PaperTradingService(sessions, "fixture", max_order_notional=Decimal("500"))
    account = service.create_account(CreateAccountCommand("测试账户", Decimal("10000")))

    order = service.submit_order(
        SubmitOrderCommand(account.id, "SSE:600000", "BUY", 100, Decimal("10"), "risk-buy")
    )

    assert order.status == "REJECTED"
    assert order.rejection_reason == "MAX_ORDER_NOTIONAL_EXCEEDED"
    assert service.list_risk_events(account.id)[0].rule_code == "MAX_ORDER_NOTIONAL_EXCEEDED"


def test_buy_is_rejected_when_single_position_limit_is_exceeded(tmp_path: Path) -> None:
    database_path = tmp_path / "position-risk.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        instrument = InstrumentModel(
            exchange="SSE", symbol="600000", name="浦发银行", board="MAIN", status="ACTIVE"
        )
        session.add(instrument)
        session.flush()
        session.add(
            MarketBarModel(
                instrument_id=instrument.id,
                timeframe="1d",
                timestamp=datetime(2026, 7, 24, tzinfo=UTC),
                open=Decimal("10"),
                high=Decimal("10"),
                low=Decimal("10"),
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
    service = PaperTradingService(
        sessions, "fixture", Decimal("1000000"), Decimal("0.05"), Decimal("0.95")
    )
    account = service.create_account(CreateAccountCommand("测试账户", Decimal("10000")))

    order = service.submit_order(
        SubmitOrderCommand(account.id, "SSE:600000", "BUY", 100, Decimal("10"), "position-limit")
    )

    assert order.status == "REJECTED"
    assert order.rejection_reason == "MAX_SINGLE_POSITION_RATIO_EXCEEDED"


def test_settlement_releases_residual_cash_for_partially_filled_buy(tmp_path: Path) -> None:
    database_path = tmp_path / "partial-settlement.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        instrument = InstrumentModel(
            exchange="SSE", symbol="600000", name="浦发银行", board="MAIN", status="ACTIVE"
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
                volume=Decimal("1000"),
                amount=None,
                source="fixture",
                observed_at=datetime.now(UTC),
                published_at=datetime.now(UTC),
                quality_status="VALID",
            )
        )
        session.commit()
    service = PaperTradingService(sessions, "fixture")
    account = service.create_account(CreateAccountCommand("测试账户", Decimal("10000")))

    order = service.submit_order(
        SubmitOrderCommand(account.id, "SSE:600000", "BUY", 200, Decimal("10"), "partial-buy")
    )
    settlement = service.settle_end_of_day(account.id)
    settled_account = service.get_account(account.id)

    assert order.status == "PARTIALLY_FILLED"
    assert order.filled_quantity == 100
    assert settlement.expired_order_count == 0
    assert settled_account is not None
    assert settled_account.cash == Decimal("7989.98")
    assert settled_account.frozen_cash == Decimal("0.00")


def test_settlement_applies_cash_dividend_once(tmp_path: Path) -> None:
    database_path = tmp_path / "dividend.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        instrument = InstrumentModel(
            exchange="SSE", symbol="600000", name="浦发银行", board="MAIN", status="ACTIVE"
        )
        session.add(instrument)
        session.flush()
        session.add(
            MarketBarModel(
                instrument_id=instrument.id,
                timeframe="1d",
                timestamp=datetime(2026, 7, 24, tzinfo=UTC),
                open=Decimal("10"),
                high=Decimal("10"),
                low=Decimal("10"),
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
    service = PaperTradingService(sessions, "fixture")
    account = service.create_account(CreateAccountCommand("测试账户", Decimal("10000")))
    with sessions() as session:
        session.add(
            PositionLotModel(
                id="lot-1", account_id=account.id, instrument_id=1, acquired_date=date(2026, 7, 23),
                remaining_quantity=100, frozen_quantity=0, cost_price=Decimal("10"),
            )
        )
        session.add(
            CorporateActionModel(
                id="action-1",
                instrument_id=1,
                action_type="CASH_DIVIDEND",
                ex_date=date(2026, 7, 24),
                cash_per_share=Decimal("0.10"),
                source="fixture",
                published_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

    first = service.settle_end_of_day(account.id)
    second = service.settle_end_of_day(account.id)
    settled_account = service.get_account(account.id)

    assert first.corporate_action_count == 1
    assert second.corporate_action_count == 0
    assert settled_account is not None
    assert settled_account.cash == Decimal("10010.00")
