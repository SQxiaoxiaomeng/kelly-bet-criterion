from decimal import Decimal

from app.domain.trading_rules import (
    Exchange,
    InstrumentRuleProfile,
    available_quantity,
    calculate_fees,
    price_limits,
    validate_order,
)


def test_t_plus_one_excludes_same_day_lots() -> None:
    lots = [("2026-07-24", 100), ("2026-07-25", 200)]

    assert available_quantity(lots, "2026-07-25") == 100


def test_price_limit_for_standard_stock_is_ten_percent() -> None:
    profile = InstrumentRuleProfile(exchange=Exchange.SSE, board="MAIN")

    assert price_limits(Decimal("10.00"), profile) == (Decimal("9.00"), Decimal("11.00"))


def test_rejects_buy_order_not_in_board_lot() -> None:
    profile = InstrumentRuleProfile(exchange=Exchange.SSE, board="MAIN")

    reason = validate_order(
        profile=profile,
        side="BUY",
        quantity=101,
        limit_price=Decimal("10.00"),
        previous_close=Decimal("10.00"),
        available_to_sell=0,
    )

    assert reason == "INVALID_LOT_SIZE"


def test_rejects_same_day_sell_when_quantity_is_not_settled() -> None:
    profile = InstrumentRuleProfile(exchange=Exchange.SSE, board="MAIN")

    reason = validate_order(
        profile=profile,
        side="SELL",
        quantity=200,
        limit_price=Decimal("10.00"),
        previous_close=Decimal("10.00"),
        available_to_sell=100,
    )

    assert reason == "INSUFFICIENT_SETTLED_QUANTITY"


def test_sse_sell_fee_includes_stamp_duty_and_transfer_fee() -> None:
    fees = calculate_fees(
        side="SELL",
        exchange=Exchange.SSE,
        price=Decimal("10.00"),
        quantity=1000,
    )

    assert fees.commission == Decimal("5.00")
    assert fees.stamp_duty == Decimal("5.00")
    assert fees.transfer_fee == Decimal("0.10")
    assert fees.total == Decimal("10.10")
