from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.trading_rules import (
    Exchange,
    InstrumentRuleProfile,
    calculate_fees,
    round_money,
    validate_order,
)
from app.infrastructure.models import (
    AccountSnapshotModel,
    AuditEventModel,
    CashLedgerModel,
    CorporateActionApplicationModel,
    CorporateActionModel,
    InstrumentModel,
    MarketBarModel,
    OrderLotFreezeModel,
    PositionLotModel,
    RiskEventModel,
    SimAccountModel,
    SimFillModel,
    SimOrderModel,
)


@dataclass(frozen=True)
class CreateAccountCommand:
    name: str
    initial_cash: Decimal


@dataclass(frozen=True)
class SubmitOrderCommand:
    account_id: str
    symbol: str
    side: str
    quantity: int
    limit_price: Decimal
    idempotency_key: str


@dataclass(frozen=True)
class PositionSummary:
    symbol: str
    quantity: int
    available_quantity: int
    frozen_quantity: int
    average_cost: Decimal


@dataclass(frozen=True)
class SettlementResult:
    expired_order_count: int
    snapshot_date: date
    corporate_action_count: int


@dataclass(frozen=True)
class CorporateActionApplicationSummary:
    corporate_action_id: str
    action_type: str
    ex_date: date
    amount: Decimal
    applied_at: datetime


class PaperTradingService:
    """Close-price paper execution with immutable fills and cash-ledger entries."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        market_source: str,
        max_order_notional: Decimal = Decimal("1000000"),
        max_single_position_ratio: Decimal = Decimal("0.50"),
        max_total_position_ratio: Decimal = Decimal("0.95"),
    ) -> None:
        self._session_factory = session_factory
        self._market_source = market_source
        self._max_order_notional = max_order_notional
        self._max_single_position_ratio = max_single_position_ratio
        self._max_total_position_ratio = max_total_position_ratio

    def create_account(self, command: CreateAccountCommand) -> SimAccountModel:
        if command.initial_cash <= 0:
            raise ValueError("INITIAL_CASH_MUST_BE_POSITIVE")
        now = datetime.now(UTC)
        account = SimAccountModel(
            id=str(uuid4()),
            name=command.name,
            cash=round_money(command.initial_cash),
            created_at=now,
        )
        with self._session_factory() as session:
            session.add(account)
            session.add(
                CashLedgerModel(
                    id=str(uuid4()),
                    account_id=account.id,
                    amount=account.cash,
                    reason="INITIAL_DEPOSIT",
                    reference_id=account.id,
                    created_at=now,
                )
            )
            self._audit(session, "ACCOUNT", "ACCOUNT_CREATED", account.id, account.id, now)
            session.commit()
            session.refresh(account)
            return account

    def submit_order(self, command: SubmitOrderCommand) -> SimOrderModel:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            existing = session.scalar(
                select(SimOrderModel).where(
                    SimOrderModel.account_id == command.account_id,
                    SimOrderModel.idempotency_key == command.idempotency_key,
                )
            )
            if existing is not None:
                return existing
            account = session.get(SimAccountModel, command.account_id)
            if account is None or account.status != "ACTIVE":
                raise ValueError("ACCOUNT_NOT_ACTIVE")
            instrument, bar = self._get_instrument_and_latest_bar(session, command.symbol)
            side = command.side.upper()
            available = self._available_quantity(
                session, account.id, instrument.id, bar.timestamp.date()
            )
            profile = InstrumentRuleProfile(
                exchange=Exchange(instrument.exchange),
                board=instrument.board,
                is_tradeable=instrument.status == "ACTIVE",
            )
            rejection = validate_order(
                profile=profile,
                side=side,
                quantity=command.quantity,
                limit_price=command.limit_price,
                previous_close=bar.close,
                available_to_sell=available,
            )
            if command.limit_price * command.quantity > self._max_order_notional:
                rejection = "MAX_ORDER_NOTIONAL_EXCEEDED"
            if rejection is None and side == "BUY":
                rejection = self._validate_position_limits(
                    session, account, instrument.id, command.limit_price * command.quantity
                )
            order = SimOrderModel(
                id=str(uuid4()),
                account_id=account.id,
                instrument_id=instrument.id,
                idempotency_key=command.idempotency_key,
                side=side,
                order_type="LIMIT",
                limit_price=command.limit_price,
                quantity=command.quantity,
                status="REJECTED" if rejection is not None else "ACCEPTED",
                rejection_reason=rejection,
                created_at=now,
                updated_at=now,
            )
            session.add(order)
            session.flush()
            if rejection is not None:
                self._record_risk_event(session, account.id, order.id, rejection, now)
                self._audit(session, "ORDER", "ORDER_REJECTED", order.id, account.id, now)
                session.commit()
                session.refresh(order)
                return order

            fees = calculate_fees(
                side=side,
                exchange=Exchange(instrument.exchange),
                price=command.limit_price,
                quantity=command.quantity,
            )
            turnover = command.limit_price * command.quantity
            if side == "BUY":
                reserve = round_money(turnover + fees.total)
                if account.cash < reserve:
                    order.status = "REJECTED"
                    order.rejection_reason = "INSUFFICIENT_CASH"
                    self._record_risk_event(session, account.id, order.id, "INSUFFICIENT_CASH", now)
                    self._audit(session, "ORDER", "ORDER_REJECTED", order.id, account.id, now)
                    session.commit()
                    session.refresh(order)
                    return order
                account.cash -= reserve
                account.frozen_cash += reserve
                order.frozen_cash = reserve
            else:
                self._freeze_sell_lots(
                    session,
                    order.id,
                    account.id,
                    instrument.id,
                    command.quantity,
                    bar.timestamp.date(),
                )
            can_fill = (side == "BUY" and command.limit_price >= bar.close) or (
                side == "SELL" and command.limit_price <= bar.close
            )
            if not can_fill:
                self._audit(session, "ORDER", "ORDER_ACCEPTED", order.id, account.id, now)
                session.commit()
                session.refresh(order)
                return order
            fill_quantity = self._executable_quantity(bar.volume, order.quantity)
            if fill_quantity == 0:
                self._audit(session, "ORDER", "ORDER_ACCEPTED", order.id, account.id, now)
                session.commit()
                session.refresh(order)
                return order
            fill_fees = calculate_fees(
                side=side,
                exchange=Exchange(instrument.exchange),
                price=command.limit_price,
                quantity=fill_quantity,
            )
            self._fill_order(
                session, order, account, bar.timestamp.date(), fill_fees.total, fill_quantity, now
            )
            action = "ORDER_FILLED" if order.status == "FILLED" else "ORDER_PARTIALLY_FILLED"
            self._audit(session, "ORDER", action, order.id, account.id, now)
            session.commit()
            session.refresh(order)
            return order

    def get_account(self, account_id: str) -> SimAccountModel | None:
        with self._session_factory() as session:
            return session.get(SimAccountModel, account_id)

    def list_accounts(self) -> list[SimAccountModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(SimAccountModel).order_by(SimAccountModel.created_at.desc())
                )
            )

    def update_account(
        self, account_id: str, name: str | None = None, status: str | None = None
    ) -> SimAccountModel:
        with self._session_factory() as session:
            account = session.get(SimAccountModel, account_id)
            if account is None:
                raise ValueError("ACCOUNT_NOT_FOUND")
            if name is not None:
                account.name = name
            if status is not None:
                if status not in {"ACTIVE", "ARCHIVED"}:
                    raise ValueError("INVALID_ACCOUNT_STATUS")
                account.status = status
            session.commit()
            session.refresh(account)
            return account

    def can_delete_account(self, account_id: str) -> bool:
        with self._session_factory() as session:
            has_orders = session.scalar(
                select(SimOrderModel.id).where(SimOrderModel.account_id == account_id).limit(1)
            )
            has_positions = session.scalar(
                select(PositionLotModel.id)
                .where(PositionLotModel.account_id == account_id)
                .limit(1)
            )
            return has_orders is None and has_positions is None

    def delete_empty_account(self, account_id: str) -> None:
        with self._session_factory() as session:
            account = session.get(SimAccountModel, account_id)
            if account is None:
                raise ValueError("ACCOUNT_NOT_FOUND")
            if not self._can_delete_account_in_session(session, account_id):
                raise ValueError("ACCOUNT_HAS_TRADING_HISTORY")
            session.execute(delete(CashLedgerModel).where(CashLedgerModel.account_id == account_id))
            session.execute(
                delete(AccountSnapshotModel).where(AccountSnapshotModel.account_id == account_id)
            )
            session.execute(delete(CorporateActionApplicationModel).where(
                CorporateActionApplicationModel.account_id == account_id
            ))
            session.execute(delete(AuditEventModel).where(AuditEventModel.account_id == account_id))
            session.delete(account)
            session.commit()

    @staticmethod
    def _can_delete_account_in_session(session: Session, account_id: str) -> bool:
        has_orders = session.scalar(
            select(SimOrderModel.id).where(SimOrderModel.account_id == account_id).limit(1)
        )
        has_positions = session.scalar(
            select(PositionLotModel.id).where(PositionLotModel.account_id == account_id).limit(1)
        )
        return has_orders is None and has_positions is None

    def list_orders(self, account_id: str) -> list[SimOrderModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(select(SimOrderModel).where(SimOrderModel.account_id == account_id))
            )

    def cancel_order(self, account_id: str, order_id: str) -> SimOrderModel:
        with self._session_factory() as session:
            order = session.get(SimOrderModel, order_id)
            if order is None or order.account_id != account_id:
                raise ValueError("ORDER_NOT_FOUND")
            if order.status not in {"ACCEPTED", "PARTIALLY_FILLED"}:
                raise ValueError("ORDER_NOT_CANCELLABLE")
            account = session.get(SimAccountModel, account_id)
            if account is None:
                raise ValueError("ACCOUNT_NOT_ACTIVE")
            if order.side == "BUY":
                account.frozen_cash -= order.frozen_cash
                account.cash += order.frozen_cash
            else:
                freezes = session.scalars(
                    select(OrderLotFreezeModel).where(
                        OrderLotFreezeModel.order_id == order.id,
                        OrderLotFreezeModel.status == "FROZEN",
                    )
                )
                for freeze in freezes:
                    lot = session.get(PositionLotModel, freeze.position_lot_id)
                    if lot is None or lot.frozen_quantity < freeze.quantity:
                        raise ValueError("FROZEN_POSITION_INCONSISTENT")
                    lot.frozen_quantity -= freeze.quantity
                    freeze.status = "RELEASED"
            order.status = "CANCELLED"
            order.updated_at = datetime.now(UTC)
            self._audit(session, "ORDER", "ORDER_CANCELLED", order.id, account.id, order.updated_at)
            session.commit()
            session.refresh(order)
            return order

    def list_positions(self, account_id: str) -> list[PositionSummary]:
        with self._session_factory() as session:
            rows = session.execute(
                select(PositionLotModel, InstrumentModel)
                .join(InstrumentModel, PositionLotModel.instrument_id == InstrumentModel.id)
                .where(
                    PositionLotModel.account_id == account_id,
                    PositionLotModel.remaining_quantity > 0,
                )
            )
            grouped: dict[str, tuple[InstrumentModel, list[PositionLotModel]]] = {}
            for lot, instrument in rows:
                symbol = f"{instrument.exchange}:{instrument.symbol}"
                grouped.setdefault(symbol, (instrument, []))[1].append(lot)
            summaries: list[PositionSummary] = []
            for symbol, (instrument, lots) in grouped.items():
                latest_bar = self._get_latest_bar_for_instrument(session, instrument.id)
                trade_date = latest_bar.timestamp.date() if latest_bar is not None else None
                summaries.append(
                    PositionSummary(
                        symbol=symbol,
                        quantity=sum(lot.remaining_quantity for lot in lots),
                        available_quantity=sum(
                            lot.remaining_quantity - lot.frozen_quantity
                            for lot in lots
                            if trade_date is not None and lot.acquired_date < trade_date
                        ),
                        frozen_quantity=sum(lot.frozen_quantity for lot in lots),
                        average_cost=sum(
                            (lot.cost_price * lot.remaining_quantity for lot in lots), Decimal("0")
                        )
                        / sum(lot.remaining_quantity for lot in lots),
                    )
                )
            return summaries

    def list_fills(self, account_id: str) -> list[SimFillModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(SimFillModel)
                    .join(SimOrderModel, SimFillModel.order_id == SimOrderModel.id)
                    .where(SimOrderModel.account_id == account_id)
                    .order_by(SimFillModel.filled_at.desc())
                )
            )

    def list_cash_ledger(self, account_id: str) -> list[CashLedgerModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(CashLedgerModel)
                    .where(CashLedgerModel.account_id == account_id)
                    .order_by(CashLedgerModel.created_at.desc())
                )
            )

    def list_account_snapshots(self, account_id: str) -> list[AccountSnapshotModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(AccountSnapshotModel)
                    .where(AccountSnapshotModel.account_id == account_id)
                    .order_by(AccountSnapshotModel.as_of_date.desc())
                )
            )

    def create_cash_dividend(
        self, symbol: str, ex_date: date, cash_per_share: Decimal, source: str = "manual"
    ) -> CorporateActionModel:
        if cash_per_share <= 0:
            raise ValueError("CASH_DIVIDEND_MUST_BE_POSITIVE")
        now = datetime.now(UTC)
        with self._session_factory() as session:
            instrument, _ = self._get_instrument_and_latest_bar(session, symbol)
            existing = session.scalar(
                select(CorporateActionModel).where(
                    CorporateActionModel.instrument_id == instrument.id,
                    CorporateActionModel.action_type == "CASH_DIVIDEND",
                    CorporateActionModel.ex_date == ex_date,
                    CorporateActionModel.source == source,
                )
            )
            if existing is not None:
                return existing
            action = CorporateActionModel(
                id=str(uuid4()),
                instrument_id=instrument.id,
                action_type="CASH_DIVIDEND",
                ex_date=ex_date,
                cash_per_share=cash_per_share,
                source=source,
                published_at=now,
                created_at=now,
            )
            session.add(action)
            session.commit()
            session.refresh(action)
            return action

    def list_corporate_action_applications(
        self, account_id: str
    ) -> list[CorporateActionApplicationSummary]:
        with self._session_factory() as session:
            rows = session.execute(
                select(CorporateActionApplicationModel, CorporateActionModel)
                .join(
                    CorporateActionModel,
                    CorporateActionApplicationModel.corporate_action_id == CorporateActionModel.id,
                )
                .where(CorporateActionApplicationModel.account_id == account_id)
                .order_by(CorporateActionApplicationModel.applied_at.desc())
            )
            return [
                CorporateActionApplicationSummary(
                    corporate_action_id=application.corporate_action_id,
                    action_type=action.action_type,
                    ex_date=action.ex_date,
                    amount=application.amount,
                    applied_at=application.applied_at,
                )
                for application, action in rows
            ]

    def list_risk_events(self, account_id: str) -> list[RiskEventModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(RiskEventModel)
                    .where(RiskEventModel.account_id == account_id)
                    .order_by(RiskEventModel.created_at.desc())
                )
            )

    def list_audit_events(self, account_id: str) -> list[AuditEventModel]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(AuditEventModel)
                    .where(AuditEventModel.account_id == account_id)
                    .order_by(AuditEventModel.created_at.desc())
                )
            )

    def list_active_account_ids(self) -> list[str]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(SimAccountModel.id).where(SimAccountModel.status == "ACTIVE")
                )
            )

    def settle_end_of_day(self, account_id: str) -> SettlementResult:
        with self._session_factory() as session:
            account = session.get(SimAccountModel, account_id)
            if account is None:
                raise ValueError("ACCOUNT_NOT_ACTIVE")
            orders = session.scalars(
                select(SimOrderModel).where(
                    SimOrderModel.account_id == account_id,
                    SimOrderModel.status.in_(("ACCEPTED", "PARTIALLY_FILLED")),
                )
            )
            expired_count = 0
            now = datetime.now(UTC)
            for order in orders:
                bar = self._get_latest_bar_for_instrument(session, order.instrument_id)
                if bar is not None and self._is_limit_executable(order, bar.close):
                    fill_quantity = self._executable_quantity(
                        bar.volume, order.quantity - order.filled_quantity
                    )
                    if fill_quantity > 0:
                        instrument = session.get(InstrumentModel, order.instrument_id)
                        if instrument is None:
                            raise ValueError("INSTRUMENT_NOT_FOUND")
                        fees = calculate_fees(
                            side=order.side,
                            exchange=Exchange(instrument.exchange),
                            price=order.limit_price,
                            quantity=fill_quantity,
                        )
                        self._fill_order(
                            session,
                            order,
                            account,
                            bar.timestamp.date(),
                            fees.total,
                            fill_quantity,
                            now,
                        )
                        self._audit(
                            session,
                            "ORDER",
                            (
                                "ORDER_FILLED"
                                if order.status == "FILLED"
                                else "ORDER_PARTIALLY_FILLED"
                            ),
                            order.id,
                            account.id,
                            now,
                        )
                if order.status == "FILLED":
                    continue
                self._release_order_freeze(session, account, order)
                order.status = "EXPIRED"
                order.updated_at = now
                self._audit(
                    session, "SETTLEMENT", "ORDER_EXPIRED", order.id, account.id, order.updated_at
                )
                expired_count += 1
            snapshot_date = self._latest_market_date(session) or now.date()
            corporate_action_count = self._apply_cash_dividends(
                session, account, snapshot_date, now
            )
            self._record_account_snapshot(session, account, snapshot_date, now)
            session.commit()
            return SettlementResult(
                expired_order_count=expired_count,
                snapshot_date=snapshot_date,
                corporate_action_count=corporate_action_count,
            )

    @staticmethod
    def _record_risk_event(
        session: Session, account_id: str, order_id: str, rule_code: str, now: datetime
    ) -> None:
        session.add(
            RiskEventModel(
                id=str(uuid4()),
                account_id=account_id,
                order_id=order_id,
                rule_code=rule_code,
                decision="REJECT",
                detail=rule_code,
                created_at=now,
            )
        )

    @staticmethod
    def _audit(
        session: Session,
        category: str,
        action: str,
        reference_id: str,
        account_id: str,
        now: datetime,
    ) -> None:
        session.add(
            AuditEventModel(
                id=str(uuid4()),
                category=category,
                action=action,
                reference_id=reference_id,
                account_id=account_id,
                detail={},
                created_at=now,
            )
        )

    @staticmethod
    def _release_order_freeze(
        session: Session, account: SimAccountModel, order: SimOrderModel
    ) -> None:
        if order.side == "BUY":
            account.frozen_cash -= order.frozen_cash
            account.cash += order.frozen_cash
            return
        freezes = session.scalars(
            select(OrderLotFreezeModel).where(
                OrderLotFreezeModel.order_id == order.id,
                OrderLotFreezeModel.status == "FROZEN",
            )
        )
        for freeze in freezes:
            lot = session.get(PositionLotModel, freeze.position_lot_id)
            if lot is None or lot.frozen_quantity < freeze.quantity:
                raise ValueError("FROZEN_POSITION_INCONSISTENT")
            lot.frozen_quantity -= freeze.quantity
            freeze.status = "RELEASED"

    def _get_instrument_and_latest_bar(
        self, session: Session, symbol: str
    ) -> tuple[InstrumentModel, MarketBarModel]:
        try:
            exchange, code = symbol.split(":", maxsplit=1)
        except ValueError as exc:
            raise ValueError("INVALID_SYMBOL_FORMAT") from exc
        instrument = session.scalar(
            select(InstrumentModel).where(
                InstrumentModel.exchange == exchange, InstrumentModel.symbol == code
            )
        )
        if instrument is None:
            raise ValueError("INSTRUMENT_NOT_FOUND")
        bar = session.scalar(
            select(MarketBarModel)
            .where(
                MarketBarModel.instrument_id == instrument.id,
                MarketBarModel.source == self._market_source,
                MarketBarModel.timeframe == "1d",
                MarketBarModel.quality_status == "VALID",
            )
            .order_by(MarketBarModel.timestamp.desc())
        )
        if bar is None:
            raise ValueError("NO_MARKET_DATA")
        return instrument, bar

    def _get_latest_bar_for_instrument(
        self, session: Session, instrument_id: int
    ) -> MarketBarModel | None:
        return session.scalar(
            select(MarketBarModel)
            .where(
                MarketBarModel.instrument_id == instrument_id,
                MarketBarModel.source == self._market_source,
                MarketBarModel.timeframe == "1d",
                MarketBarModel.quality_status == "VALID",
            )
            .order_by(MarketBarModel.timestamp.desc())
        )

    @staticmethod
    def _is_limit_executable(order: SimOrderModel, market_price: Decimal) -> bool:
        return (order.side == "BUY" and order.limit_price >= market_price) or (
            order.side == "SELL" and order.limit_price <= market_price
        )

    def _latest_market_date(self, session: Session) -> date | None:
        timestamp = session.scalar(
            select(MarketBarModel.timestamp)
            .where(
                MarketBarModel.source == self._market_source,
                MarketBarModel.timeframe == "1d",
                MarketBarModel.quality_status == "VALID",
            )
            .order_by(MarketBarModel.timestamp.desc())
        )
        return timestamp.date() if timestamp is not None else None

    def _validate_position_limits(
        self, session: Session, account: SimAccountModel, instrument_id: int, proposed: Decimal
    ) -> str | None:
        total_market_value = Decimal("0")
        instrument_market_value = Decimal("0")
        lots = session.scalars(
            select(PositionLotModel).where(
                PositionLotModel.account_id == account.id,
                PositionLotModel.remaining_quantity > 0,
            )
        )
        for lot in lots:
            bar = session.scalar(
                select(MarketBarModel.close)
                .where(
                    MarketBarModel.instrument_id == lot.instrument_id,
                    MarketBarModel.source == self._market_source,
                    MarketBarModel.timeframe == "1d",
                    MarketBarModel.quality_status == "VALID",
                )
                .order_by(MarketBarModel.timestamp.desc())
            )
            if bar is None:
                continue
            value = bar * lot.remaining_quantity
            total_market_value += value
            if lot.instrument_id == instrument_id:
                instrument_market_value += value
        equity = account.cash + account.frozen_cash + total_market_value
        if equity <= 0:
            return "NON_POSITIVE_ACCOUNT_EQUITY"
        if instrument_market_value + proposed > equity * self._max_single_position_ratio:
            return "MAX_SINGLE_POSITION_RATIO_EXCEEDED"
        if total_market_value + proposed > equity * self._max_total_position_ratio:
            return "MAX_TOTAL_POSITION_RATIO_EXCEEDED"
        return None

    def _record_account_snapshot(
        self, session: Session, account: SimAccountModel, as_of_date: date, now: datetime
    ) -> None:
        if session.scalar(
            select(AccountSnapshotModel.id).where(
                AccountSnapshotModel.account_id == account.id,
                AccountSnapshotModel.as_of_date == as_of_date,
            )
        ) is not None:
            return
        market_value = Decimal("0")
        lots = session.scalars(
            select(PositionLotModel).where(
                PositionLotModel.account_id == account.id,
                PositionLotModel.remaining_quantity > 0,
            )
        )
        for lot in lots:
            bar = session.scalar(
                select(MarketBarModel)
                .where(
                    MarketBarModel.instrument_id == lot.instrument_id,
                    MarketBarModel.source == self._market_source,
                    MarketBarModel.timeframe == "1d",
                    MarketBarModel.quality_status == "VALID",
                    MarketBarModel.timestamp
                    <= datetime.combine(as_of_date, datetime.max.time(), UTC),
                )
                .order_by(MarketBarModel.timestamp.desc())
            )
            if bar is not None:
                market_value += bar.close * lot.remaining_quantity
        market_value = round_money(market_value)
        equity = round_money(account.cash + account.frozen_cash + market_value)
        session.add(
            AccountSnapshotModel(
                id=str(uuid4()),
                account_id=account.id,
                as_of_date=as_of_date,
                cash=round_money(account.cash),
                frozen_cash=round_money(account.frozen_cash),
                market_value=market_value,
                equity=equity,
                created_at=now,
            )
        )

    @staticmethod
    def _apply_cash_dividends(
        session: Session, account: SimAccountModel, as_of_date: date, now: datetime
    ) -> int:
        actions = session.scalars(
            select(CorporateActionModel).where(
                CorporateActionModel.action_type == "CASH_DIVIDEND",
                CorporateActionModel.ex_date <= as_of_date,
            )
        )
        applied_count = 0
        for action in actions:
            already_applied = session.scalar(
                select(CorporateActionApplicationModel.id).where(
                    CorporateActionApplicationModel.account_id == account.id,
                    CorporateActionApplicationModel.corporate_action_id == action.id,
                )
            )
            if already_applied is not None:
                continue
            lots = session.scalars(
                select(PositionLotModel).where(
                    PositionLotModel.account_id == account.id,
                    PositionLotModel.instrument_id == action.instrument_id,
                    PositionLotModel.acquired_date < action.ex_date,
                )
            )
            quantity = sum(lot.remaining_quantity for lot in lots)
            if quantity == 0:
                continue
            amount = round_money(action.cash_per_share * quantity)
            if amount <= 0:
                continue
            account.cash += amount
            session.add(
                CorporateActionApplicationModel(
                    id=str(uuid4()),
                    account_id=account.id,
                    corporate_action_id=action.id,
                    amount=amount,
                    applied_at=now,
                )
            )
            session.add(
                CashLedgerModel(
                    id=str(uuid4()),
                    account_id=account.id,
                    amount=amount,
                    reason="CASH_DIVIDEND",
                    reference_id=action.id,
                    created_at=now,
                )
            )
            PaperTradingService._audit(
                session, "CORPORATE_ACTION", "CASH_DIVIDEND_APPLIED", action.id, account.id, now
            )
            applied_count += 1
        return applied_count

    @staticmethod
    def _available_quantity(
        session: Session, account_id: str, instrument_id: int, trade_date: date
    ) -> int:
        lots = session.scalars(
            select(PositionLotModel).where(
                PositionLotModel.account_id == account_id,
                PositionLotModel.instrument_id == instrument_id,
                PositionLotModel.acquired_date < trade_date,
            )
        )
        return sum(lot.remaining_quantity - lot.frozen_quantity for lot in lots)

    @staticmethod
    def _freeze_sell_lots(
        session: Session,
        order_id: str,
        account_id: str,
        instrument_id: int,
        quantity: int,
        trade_date: date,
    ) -> None:
        remaining = quantity
        lots = session.scalars(
            select(PositionLotModel)
            .where(
                PositionLotModel.account_id == account_id,
                PositionLotModel.instrument_id == instrument_id,
                PositionLotModel.acquired_date < trade_date,
            )
            .order_by(PositionLotModel.acquired_date)
        )
        for lot in lots:
            available = lot.remaining_quantity - lot.frozen_quantity
            frozen = min(available, remaining)
            lot.frozen_quantity += frozen
            session.add(
                OrderLotFreezeModel(
                    id=str(uuid4()), order_id=order_id, position_lot_id=lot.id, quantity=frozen
                )
            )
            remaining -= frozen
            if remaining == 0:
                return
        raise ValueError("INSUFFICIENT_SETTLED_QUANTITY")

    @staticmethod
    def _fill_order(
        session: Session,
        order: SimOrderModel,
        account: SimAccountModel,
        trade_date: date,
        fee: Decimal,
        fill_quantity: int,
        now: datetime,
    ) -> None:
        turnover = order.limit_price * fill_quantity
        if order.side == "BUY":
            total = round_money(turnover + fee)
            frozen_consumption = min(total, order.frozen_cash)
            additional_cash_required = total - frozen_consumption
            if account.cash < additional_cash_required:
                raise ValueError("INSUFFICIENT_CASH_FOR_PARTIAL_FILL_FEE")
            account.frozen_cash -= frozen_consumption
            order.frozen_cash -= frozen_consumption
            account.cash -= additional_cash_required
            session.add(
                PositionLotModel(
                    id=str(uuid4()),
                    account_id=account.id,
                    instrument_id=order.instrument_id,
                    acquired_date=trade_date,
                    remaining_quantity=fill_quantity,
                    cost_price=order.limit_price,
                )
            )
            ledger_amount = -total
        else:
            PaperTradingService._consume_frozen_lots(session, order, fill_quantity)
            ledger_amount = round_money(turnover - fee)
            account.cash += ledger_amount
        order.filled_quantity += fill_quantity
        order.status = "FILLED" if order.filled_quantity == order.quantity else "PARTIALLY_FILLED"
        order.updated_at = now
        session.add(
            SimFillModel(
                id=str(uuid4()),
                order_id=order.id,
                price=order.limit_price,
                quantity=fill_quantity,
                fee=fee,
                filled_at=now,
            )
        )
        session.add(
            CashLedgerModel(
                id=str(uuid4()),
                account_id=account.id,
                amount=ledger_amount,
                reason="ORDER_FILL",
                reference_id=order.id,
                created_at=now,
            )
        )

    @staticmethod
    def _consume_frozen_lots(session: Session, order: SimOrderModel, quantity: int) -> None:
        freezes = session.scalars(
            select(OrderLotFreezeModel).where(
                OrderLotFreezeModel.order_id == order.id,
                OrderLotFreezeModel.status == "FROZEN",
            )
        )
        remaining = quantity
        for freeze in freezes:
            if remaining == 0:
                break
            lot = session.get(PositionLotModel, freeze.position_lot_id)
            consumed = min(freeze.quantity, remaining)
            if lot is None or lot.frozen_quantity < consumed:
                raise ValueError("FROZEN_POSITION_INCONSISTENT")
            lot.frozen_quantity -= consumed
            lot.remaining_quantity -= consumed
            freeze.quantity -= consumed
            if freeze.quantity == 0:
                freeze.status = "CONSUMED"
            remaining -= consumed
        if remaining != 0:
            raise ValueError("FROZEN_POSITION_INCONSISTENT")

    @staticmethod
    def _executable_quantity(volume: Decimal, requested_quantity: int) -> int:
        capacity = int(volume * Decimal("0.10"))
        lot_capacity = (capacity // 100) * 100
        return min(requested_quantity, lot_capacity)
