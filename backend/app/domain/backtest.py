from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from math import sqrt
from statistics import fmean, pstdev

from app.domain.trading_rules import Exchange, FeeSchedule, calculate_fees


@dataclass(frozen=True)
class DailyBar:
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class Trade:
    trade_date: date
    side: str
    price: Decimal
    quantity: int
    fee: Decimal


@dataclass(frozen=True)
class EquityPoint:
    trade_date: date
    equity: Decimal


@dataclass(frozen=True)
class BacktestMetrics:
    total_return: Decimal
    max_drawdown: Decimal
    volatility: Decimal
    trade_count: int
    total_fees: Decimal
    annualized_sharpe: Decimal
    turnover: Decimal


@dataclass(frozen=True)
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    metrics: BacktestMetrics


def _buy_quantity(cash: Decimal, price: Decimal, exchange: Exchange, schedule: FeeSchedule) -> int:
    quantity = int((cash / price / Decimal("100")).to_integral_value(rounding=ROUND_DOWN)) * 100
    while quantity > 0:
        fees = calculate_fees(
            side="BUY", exchange=exchange, price=price, quantity=quantity, schedule=schedule
        )
        if price * quantity + fees.total <= cash:
            return quantity
        quantity -= 100
    return 0


def _moving_average(values: list[Decimal], window: int) -> Decimal | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / Decimal(window)


def run_moving_average_backtest(
    *,
    bars: list[DailyBar],
    initial_cash: Decimal,
    short_window: int,
    long_window: int,
    exchange: Exchange,
    schedule: FeeSchedule = FeeSchedule(),
) -> BacktestResult:
    """Long-only daily backtest: signals at close, execution at the next open."""
    if initial_cash <= 0:
        raise ValueError("INITIAL_CASH_MUST_BE_POSITIVE")
    if short_window <= 0 or long_window <= 0 or short_window >= long_window:
        raise ValueError("INVALID_MOVING_AVERAGE_WINDOWS")
    if not bars:
        raise ValueError("NO_MARKET_DATA")

    cash = initial_cash
    quantity = 0
    pending_side: str | None = None
    closes: list[Decimal] = []
    trades: list[Trade] = []
    equity_curve: list[EquityPoint] = []

    for bar in bars:
        if pending_side == "BUY" and quantity == 0:
            buy_quantity = _buy_quantity(cash, bar.open, exchange, schedule)
            if buy_quantity > 0:
                fees = calculate_fees(
                    side="BUY",
                    exchange=exchange,
                    price=bar.open,
                    quantity=buy_quantity,
                    schedule=schedule,
                )
                cash -= bar.open * buy_quantity + fees.total
                quantity = buy_quantity
                trades.append(Trade(bar.trade_date, "BUY", bar.open, buy_quantity, fees.total))
        elif pending_side == "SELL" and quantity > 0:
            fees = calculate_fees(
                side="SELL", exchange=exchange, price=bar.open, quantity=quantity, schedule=schedule
            )
            cash += bar.open * quantity - fees.total
            trades.append(Trade(bar.trade_date, "SELL", bar.open, quantity, fees.total))
            quantity = 0

        closes.append(bar.close)
        short_average = _moving_average(closes, short_window)
        long_average = _moving_average(closes, long_window)
        pending_side = None
        if short_average is not None and long_average is not None:
            if short_average > long_average and quantity == 0:
                pending_side = "BUY"
            elif short_average <= long_average and quantity > 0:
                pending_side = "SELL"

        equity_curve.append(EquityPoint(bar.trade_date, cash + bar.close * quantity))

    return BacktestResult(
        trades=trades,
        equity_curve=equity_curve,
        metrics=_calculate_metrics(initial_cash, trades, equity_curve),
    )


def run_buy_and_hold_backtest(
    *,
    bars: list[DailyBar],
    initial_cash: Decimal,
    exchange: Exchange,
    schedule: FeeSchedule = FeeSchedule(),
) -> BacktestResult:
    """Baseline strategy: buy the first available open and hold to sample end."""
    if initial_cash <= 0:
        raise ValueError("INITIAL_CASH_MUST_BE_POSITIVE")
    if not bars:
        raise ValueError("NO_MARKET_DATA")

    first_bar = bars[0]
    quantity = _buy_quantity(initial_cash, first_bar.open, exchange, schedule)
    fees = calculate_fees(
        side="BUY", exchange=exchange, price=first_bar.open, quantity=quantity, schedule=schedule
    )
    cash = initial_cash - first_bar.open * quantity - fees.total
    trades = (
        [Trade(first_bar.trade_date, "BUY", first_bar.open, quantity, fees.total)]
        if quantity > 0
        else []
    )
    equity_curve = [EquityPoint(bar.trade_date, cash + bar.close * quantity) for bar in bars]
    return BacktestResult(
        trades=trades,
        equity_curve=equity_curve,
        metrics=_calculate_metrics(initial_cash, trades, equity_curve),
    )


def run_grid_backtest(
    *,
    bars: list[DailyBar],
    initial_cash: Decimal,
    grid_step_percent: Decimal,
    exchange: Exchange,
    schedule: FeeSchedule = FeeSchedule(),
) -> BacktestResult:
    """Long-only grid: close crosses a grid step, then trade at next open."""
    if initial_cash <= 0 or grid_step_percent <= 0 or grid_step_percent >= Decimal("0.50"):
        raise ValueError("INVALID_GRID_STEP_PERCENT")
    if not bars:
        raise ValueError("NO_MARKET_DATA")
    cash, quantity, anchor = initial_cash, 0, bars[0].close
    pending: str | None = None
    trades: list[Trade] = []
    curve: list[EquityPoint] = []
    for bar in bars:
        if pending == "BUY":
            buy_quantity = _buy_quantity(cash / Decimal("4"), bar.open, exchange, schedule)
            if buy_quantity > 0:
                fees = calculate_fees(
                    side="BUY",
                    exchange=exchange,
                    price=bar.open,
                    quantity=buy_quantity,
                    schedule=schedule,
                )
                cash -= bar.open * buy_quantity + fees.total
                quantity += buy_quantity
                trades.append(Trade(bar.trade_date, "BUY", bar.open, buy_quantity, fees.total))
                anchor = bar.open
        elif pending == "SELL" and quantity > 0:
            sell_quantity = max(100, quantity // 4 // 100 * 100)
            sell_quantity = min(sell_quantity, quantity)
            fees = calculate_fees(
                side="SELL",
                exchange=exchange,
                price=bar.open,
                quantity=sell_quantity,
                schedule=schedule,
            )
            cash += bar.open * sell_quantity - fees.total
            quantity -= sell_quantity
            trades.append(Trade(bar.trade_date, "SELL", bar.open, sell_quantity, fees.total))
            anchor = bar.open
        pending = (
            "BUY"
            if bar.close <= anchor * (Decimal("1") - grid_step_percent)
            else "SELL"
            if quantity > 0 and bar.close >= anchor * (Decimal("1") + grid_step_percent)
            else None
        )
        curve.append(EquityPoint(bar.trade_date, cash + bar.close * quantity))
    return BacktestResult(
        trades=trades, equity_curve=curve, metrics=_calculate_metrics(initial_cash, trades, curve)
    )


def _calculate_metrics(
    initial_cash: Decimal, trades: list[Trade], equity_curve: list[EquityPoint]
) -> BacktestMetrics:
    final_equity = equity_curve[-1].equity
    total_return = (final_equity / initial_cash) - Decimal("1")
    high_water_mark = initial_cash
    max_drawdown = Decimal("0")
    returns: list[float] = []
    previous_equity = initial_cash
    for point in equity_curve:
        high_water_mark = max(high_water_mark, point.equity)
        drawdown = (point.equity / high_water_mark) - Decimal("1")
        max_drawdown = min(max_drawdown, drawdown)
        returns.append(float((point.equity / previous_equity) - Decimal("1")))
        previous_equity = point.equity
    volatility = Decimal(str(pstdev(returns))) if len(returns) > 1 else Decimal("0")
    annualized_sharpe = (
        Decimal(str(fmean(returns) / float(volatility) * sqrt(252)))
        if volatility > Decimal("0")
        else Decimal("0")
    )
    total_fees = sum((trade.fee for trade in trades), Decimal("0"))
    turnover = sum((trade.price * trade.quantity for trade in trades), Decimal("0")) / initial_cash
    return BacktestMetrics(
        total_return=total_return,
        max_drawdown=max_drawdown,
        volatility=volatility,
        trade_count=len(trades),
        total_fees=total_fees,
        annualized_sharpe=annualized_sharpe,
        turnover=turnover,
    )
