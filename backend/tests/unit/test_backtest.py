from datetime import date
from decimal import Decimal

from app.domain.backtest import DailyBar, run_buy_and_hold_backtest, run_moving_average_backtest
from app.domain.trading_rules import Exchange


def test_moving_average_signal_executes_on_next_open_not_same_close() -> None:
    bars = [
        DailyBar(
            date(2026, 7, 20),
            Decimal("10"),
            Decimal("10"),
            Decimal("10"),
            Decimal("10"),
            Decimal("1"),
        ),
        DailyBar(
            date(2026, 7, 21),
            Decimal("10"),
            Decimal("10"),
            Decimal("10"),
            Decimal("11"),
            Decimal("1"),
        ),
        DailyBar(
            date(2026, 7, 22),
            Decimal("12"),
            Decimal("12"),
            Decimal("12"),
            Decimal("12"),
            Decimal("1"),
        ),
    ]

    result = run_moving_average_backtest(
        bars=bars,
        initial_cash=Decimal("10000"),
        short_window=1,
        long_window=2,
        exchange=Exchange.SSE,
    )

    assert len(result.trades) == 1
    assert result.trades[0].trade_date == date(2026, 7, 22)
    assert result.trades[0].price == Decimal("12")


def test_buy_and_hold_buys_at_first_open_and_holds_to_end() -> None:
    bars = [
        DailyBar(
            trade_date=date(2026, 7, 20),
            open=Decimal("10"),
            high=Decimal("10"),
            low=Decimal("10"),
            close=Decimal("10"),
            volume=Decimal("1"),
        ),
        DailyBar(
            trade_date=date(2026, 7, 21),
            open=Decimal("10"),
            high=Decimal("12"),
            low=Decimal("10"),
            close=Decimal("12"),
            volume=Decimal("1"),
        ),
    ]

    result = run_buy_and_hold_backtest(
        bars=bars,
        initial_cash=Decimal("10000"),
        exchange=Exchange.SSE,
    )

    assert result.trades[0].side == "BUY"
    assert result.trades[0].trade_date == date(2026, 7, 20)
    assert result.metrics.trade_count == 1
    assert result.metrics.total_return > Decimal("0")
