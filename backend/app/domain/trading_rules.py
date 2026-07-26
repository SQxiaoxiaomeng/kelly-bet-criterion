from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

TWO_DECIMALS = Decimal("0.01")


class Exchange(StrEnum):
    SSE = "SSE"
    SZSE = "SZSE"


@dataclass(frozen=True)
class InstrumentRuleProfile:
    exchange: Exchange
    board: str
    is_st: bool = False
    is_tradeable: bool = True


@dataclass(frozen=True)
class FeeSchedule:
    commission_rate: Decimal = Decimal("0.0003")
    minimum_commission: Decimal = Decimal("5.00")
    stamp_duty_rate: Decimal = Decimal("0.0005")
    transfer_fee_rate: Decimal = Decimal("0.00001")


@dataclass(frozen=True)
class TradingFees:
    commission: Decimal
    stamp_duty: Decimal
    transfer_fee: Decimal

    @property
    def total(self) -> Decimal:
        return self.commission + self.stamp_duty + self.transfer_fee


def round_money(value: Decimal) -> Decimal:
    return value.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


def price_limit_ratio(profile: InstrumentRuleProfile) -> Decimal:
    """Return the configurable MVP price-limit ratio for a standard A-share profile."""
    if profile.is_st:
        return Decimal("0.05")
    if profile.board.upper() in {"STAR", "CHINEXT"}:
        return Decimal("0.20")
    return Decimal("0.10")


def price_limits(
    previous_close: Decimal, profile: InstrumentRuleProfile
) -> tuple[Decimal, Decimal]:
    ratio = price_limit_ratio(profile)
    lower = (previous_close * (Decimal("1") - ratio)).quantize(TWO_DECIMALS, ROUND_HALF_UP)
    upper = (previous_close * (Decimal("1") + ratio)).quantize(TWO_DECIMALS, ROUND_HALF_UP)
    return lower, upper


def is_valid_lot(side: str, quantity: int, lot_size: int = 100) -> bool:
    if quantity <= 0:
        return False
    if side.upper() == "BUY":
        return quantity % lot_size == 0
    return True


def available_quantity(lots: list[tuple[str, int]], trade_date: str) -> int:
    """Lots bought on the current trade date are locked by the A-share T+1 rule."""
    return sum(quantity for acquired_date, quantity in lots if acquired_date < trade_date)


def calculate_fees(
    *,
    side: str,
    exchange: Exchange,
    price: Decimal,
    quantity: int,
    schedule: FeeSchedule = FeeSchedule(),
) -> TradingFees:
    turnover = price * Decimal(quantity)
    commission = max(turnover * schedule.commission_rate, schedule.minimum_commission)
    stamp_duty = turnover * schedule.stamp_duty_rate if side.upper() == "SELL" else Decimal("0")
    transfer_fee = (
        turnover * schedule.transfer_fee_rate if exchange is Exchange.SSE else Decimal("0")
    )
    return TradingFees(
        commission=round_money(commission),
        stamp_duty=round_money(stamp_duty),
        transfer_fee=round_money(transfer_fee),
    )


def validate_order(
    *,
    profile: InstrumentRuleProfile,
    side: str,
    quantity: int,
    limit_price: Decimal,
    previous_close: Decimal,
    available_to_sell: int,
) -> str | None:
    if not profile.is_tradeable:
        return "INSTRUMENT_NOT_TRADEABLE"
    if not is_valid_lot(side, quantity):
        return "INVALID_LOT_SIZE"
    lower, upper = price_limits(previous_close, profile)
    if limit_price < lower or limit_price > upper:
        return "PRICE_OUTSIDE_LIMIT"
    if side.upper() == "SELL" and quantity > available_to_sell:
        return "INSUFFICIENT_SETTLED_QUANTITY"
    return None
