import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from app.application.paper_trading import (
    CreateAccountCommand,
    PaperTradingService,
    SubmitOrderCommand,
)
from app.core.config import get_settings
from app.infrastructure.database import create_session_factory
from app.infrastructure.models import SimAccountModel, SimOrderModel

router = APIRouter(prefix="/sim", tags=["simulated-trading"])


class CreateAccountRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    initial_cash: Decimal = Field(gt=0)


class AccountResponse(BaseModel):
    id: str
    name: str
    status: str
    cash: Decimal
    frozen_cash: Decimal
    created_at: datetime
    can_delete: bool


class UpdateAccountRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: Literal["ACTIVE", "ARCHIVED"] | None = None


class CreateOrderRequest(BaseModel):
    symbol: str
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)
    limit_price: Decimal = Field(gt=0)


class OrderResponse(BaseModel):
    id: str
    account_id: str
    side: str
    quantity: int
    filled_quantity: int
    limit_price: Decimal
    status: str
    rejection_reason: str | None


class PositionResponse(BaseModel):
    symbol: str
    quantity: int
    available_quantity: int
    frozen_quantity: int
    average_cost: Decimal


class RiskEventResponse(BaseModel):
    id: str
    order_id: str | None
    rule_code: str
    decision: str
    detail: str


class SettlementResponse(BaseModel):
    expired_order_count: int
    snapshot_date: date
    corporate_action_count: int


class FillResponse(BaseModel):
    id: str
    order_id: str
    price: Decimal
    quantity: int
    fee: Decimal
    filled_at: datetime


class CashLedgerResponse(BaseModel):
    id: str
    amount: Decimal
    reason: str
    reference_id: str
    created_at: datetime


class AccountSnapshotResponse(BaseModel):
    as_of_date: date
    cash: Decimal
    frozen_cash: Decimal
    market_value: Decimal
    equity: Decimal


class CreateCashDividendRequest(BaseModel):
    symbol: str
    ex_date: date
    cash_per_share: Decimal = Field(gt=0)


class CorporateActionResponse(BaseModel):
    id: str
    action_type: str
    ex_date: date
    cash_per_share: Decimal
    source: str


class CorporateActionApplicationResponse(BaseModel):
    corporate_action_id: str
    action_type: str
    ex_date: date
    amount: Decimal
    applied_at: datetime


class AuditEventResponse(BaseModel):
    id: str
    category: str
    action: str
    reference_id: str
    detail: dict[str, str | int]


def _service() -> PaperTradingService:
    settings = get_settings()
    return PaperTradingService(
        create_session_factory(),
        settings.market_data_provider,
        settings.max_order_notional,
        settings.max_single_position_ratio,
        settings.max_total_position_ratio,
    )


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: CreateAccountRequest) -> AccountResponse:
    try:
        account = _service().create_account(
            CreateAccountCommand(payload.name, payload.initial_cash)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_account_response(account, can_delete=True)


@router.get("/accounts", response_model=list[AccountResponse])
def list_accounts() -> list[AccountResponse]:
    service = _service()
    return [
        _to_account_response(account, can_delete=service.can_delete_account(account.id))
        for account in service.list_accounts()
    ]


@router.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(account_id: str) -> AccountResponse:
    account = _service().get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="ACCOUNT_NOT_FOUND")
    return _to_account_response(account, can_delete=_service().can_delete_account(account.id))


@router.patch("/accounts/{account_id}", response_model=AccountResponse)
def update_account(account_id: str, payload: UpdateAccountRequest) -> AccountResponse:
    if payload.name is None and payload.status is None:
        raise HTTPException(status_code=422, detail="ACCOUNT_UPDATE_REQUIRED")
    try:
        service = _service()
        account = service.update_account(account_id, payload.name, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_account_response(account, can_delete=_service().can_delete_account(account.id))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: str) -> None:
    try:
        _service().delete_empty_account(account_id)
    except ValueError as exc:
        error_status = 404 if str(exc) == "ACCOUNT_NOT_FOUND" else 409
        raise HTTPException(status_code=error_status, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/orders", response_model=OrderResponse)
def submit_order(
    account_id: str,
    payload: CreateOrderRequest,
    idempotency_key: str = Header(min_length=1, max_length=128),
) -> OrderResponse:
    try:
        order = _service().submit_order(
            SubmitOrderCommand(
                account_id=account_id,
                symbol=payload.symbol,
                side=payload.side,
                quantity=payload.quantity,
                limit_price=payload.limit_price,
                idempotency_key=idempotency_key,
            )
        )
    except ValueError as exc:
        error_status = 404 if str(exc) in {"ACCOUNT_NOT_ACTIVE", "INSTRUMENT_NOT_FOUND"} else 422
        raise HTTPException(status_code=error_status, detail=str(exc)) from exc
    return _to_order_response(order)


@router.get("/accounts/{account_id}/orders", response_model=list[OrderResponse])
def list_orders(account_id: str) -> list[OrderResponse]:
    return [_to_order_response(order) for order in _service().list_orders(account_id)]


@router.get("/accounts/{account_id}/positions", response_model=list[PositionResponse])
def list_positions(account_id: str) -> list[PositionResponse]:
    return [
        PositionResponse.model_validate(position, from_attributes=True)
        for position in _service().list_positions(account_id)
    ]


@router.get("/accounts/{account_id}/fills", response_model=list[FillResponse])
def list_fills(account_id: str) -> list[FillResponse]:
    return [
        FillResponse.model_validate(fill, from_attributes=True)
        for fill in _service().list_fills(account_id)
    ]


@router.get("/accounts/{account_id}/cash-ledger", response_model=list[CashLedgerResponse])
def list_cash_ledger(account_id: str) -> list[CashLedgerResponse]:
    return [
        CashLedgerResponse.model_validate(entry, from_attributes=True)
        for entry in _service().list_cash_ledger(account_id)
    ]


@router.get("/accounts/{account_id}/snapshots", response_model=list[AccountSnapshotResponse])
def list_account_snapshots(account_id: str) -> list[AccountSnapshotResponse]:
    return [
        AccountSnapshotResponse.model_validate(snapshot, from_attributes=True)
        for snapshot in _service().list_account_snapshots(account_id)
    ]


@router.post("/corporate-actions/cash-dividends", response_model=CorporateActionResponse)
def create_cash_dividend(payload: CreateCashDividendRequest) -> CorporateActionResponse:
    try:
        action = _service().create_cash_dividend(
            payload.symbol, payload.ex_date, payload.cash_per_share
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CorporateActionResponse.model_validate(action, from_attributes=True)


@router.get(
    "/accounts/{account_id}/corporate-action-applications",
    response_model=list[CorporateActionApplicationResponse],
)
def list_corporate_action_applications(
    account_id: str,
) -> list[CorporateActionApplicationResponse]:
    return [
        CorporateActionApplicationResponse.model_validate(application, from_attributes=True)
        for application in _service().list_corporate_action_applications(account_id)
    ]


@router.websocket("/accounts/{account_id}/stream")
async def stream_account_state(websocket: WebSocket, account_id: str) -> None:
    """Local-mode polling stream; REST remains the source of truth after reconnects."""
    await websocket.accept()
    previous_payload: str | None = None
    try:
        while True:
            service = _service()
            account = service.get_account(account_id)
            if account is None:
                await websocket.close(code=4404)
                return
            payload = {
                "type": "account_state",
                "account": _to_account_response(account).model_dump(mode="json"),
                "orders": [
                    _to_order_response(order).model_dump(mode="json")
                    for order in service.list_orders(account_id)
                ],
                "positions": [
                    PositionResponse.model_validate(
                        position, from_attributes=True
                    ).model_dump(mode="json")
                    for position in service.list_positions(account_id)
                ],
                "risk_event_count": len(service.list_risk_events(account_id)),
            }
            serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            if serialized != previous_payload:
                await websocket.send_json(payload)
                previous_payload = serialized
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


@router.get("/accounts/{account_id}/risk-events", response_model=list[RiskEventResponse])
def list_risk_events(account_id: str) -> list[RiskEventResponse]:
    return [
        RiskEventResponse.model_validate(event, from_attributes=True)
        for event in _service().list_risk_events(account_id)
    ]


@router.post("/accounts/{account_id}/settle", response_model=SettlementResponse)
def settle_end_of_day(account_id: str) -> SettlementResponse:
    try:
        result = _service().settle_end_of_day(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SettlementResponse(
        expired_order_count=result.expired_order_count,
        snapshot_date=result.snapshot_date,
        corporate_action_count=result.corporate_action_count,
    )


@router.get("/accounts/{account_id}/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(account_id: str) -> list[AuditEventResponse]:
    return [
        AuditEventResponse.model_validate(event, from_attributes=True)
        for event in _service().list_audit_events(account_id)
    ]


@router.post("/accounts/{account_id}/orders/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(account_id: str, order_id: str) -> OrderResponse:
    try:
        order = _service().cancel_order(account_id, order_id)
    except ValueError as exc:
        error_status = 404 if str(exc) == "ORDER_NOT_FOUND" else 409
        raise HTTPException(status_code=error_status, detail=str(exc)) from exc
    return _to_order_response(order)


def _to_account_response(account: SimAccountModel, can_delete: bool = False) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        status=account.status,
        cash=account.cash,
        frozen_cash=account.frozen_cash,
        created_at=account.created_at,
        can_delete=can_delete,
    )


def _to_order_response(order: SimOrderModel) -> OrderResponse:
    return OrderResponse(
        id=order.id,
        account_id=order.account_id,
        side=order.side,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        limit_price=order.limit_price,
        status=order.status,
        rejection_reason=order.rejection_reason,
    )
