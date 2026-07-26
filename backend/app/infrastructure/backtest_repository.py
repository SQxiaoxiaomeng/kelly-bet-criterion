from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.application.backtests import BacktestRequest, StoredBacktest
from app.domain.backtest import BacktestMetrics, BacktestResult, DailyBar, EquityPoint, Trade
from app.infrastructure.models import BacktestRunModel, DataSnapshotModel


class SqlAlchemyBacktestRepository:
    """PostgreSQL/SQLite implementation for immutable completed backtest reports."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def save(self, run: StoredBacktest) -> None:
        with self._session_factory() as session:
            if session.get(DataSnapshotModel, run.data_snapshot_id) is None:
                session.add(
                    DataSnapshotModel(
                        id=run.data_snapshot_id,
                        source_versions={"snapshot_id": run.data_snapshot_id},
                        created_at=datetime.now(UTC),
                    )
                )
            session.add(_serialize_run(run))
            session.commit()

    def get(self, run_id: UUID) -> StoredBacktest | None:
        with self._session_factory() as session:
            record = session.get(BacktestRunModel, str(run_id))
            return _deserialize_run(record) if record is not None else None


def _serialize_run(run: StoredBacktest) -> BacktestRunModel:
    return BacktestRunModel(
        id=str(run.id),
        status="COMPLETED",
        strategy_name=run.strategy_name,
        strategy_version=run.strategy_version,
        data_snapshot_id=run.data_snapshot_id,
        configuration={
            "symbol": run.request.symbol,
            "start": run.request.start.isoformat(),
            "end": run.request.end.isoformat(),
            "initial_cash": str(run.request.initial_cash),
            "short_window": run.request.short_window,
            "long_window": run.request.long_window,
            "strategy_name": run.strategy_name,
            "strategy_version": run.strategy_version,
            "grid_step_percent": str(run.request.grid_step_percent),
            "daily_bars": [
                {
                    "trade_date": bar.trade_date.isoformat(),
                    "open": str(bar.open),
                    "high": str(bar.high),
                    "low": str(bar.low),
                    "close": str(bar.close),
                    "volume": str(bar.volume),
                }
                for bar in run.daily_bars
            ],
        },
        metrics={
            "total_return": str(run.result.metrics.total_return),
            "max_drawdown": str(run.result.metrics.max_drawdown),
            "volatility": str(run.result.metrics.volatility),
            "trade_count": run.result.metrics.trade_count,
            "total_fees": str(run.result.metrics.total_fees),
            "annualized_sharpe": str(run.result.metrics.annualized_sharpe),
            "turnover": str(run.result.metrics.turnover),
        },
        trades=[
            {
                "trade_date": trade.trade_date.isoformat(),
                "side": trade.side,
                "price": str(trade.price),
                "quantity": trade.quantity,
                "fee": str(trade.fee),
            }
            for trade in run.result.trades
        ],
        equity_curve=[
            {"trade_date": point.trade_date.isoformat(), "equity": str(point.equity)}
            for point in run.result.equity_curve
        ],
        created_at=datetime.now(UTC),
    )


def _deserialize_run(record: BacktestRunModel) -> StoredBacktest:
    config = record.configuration
    metrics = record.metrics
    daily_bar_payloads = cast(list[dict[str, str]], config.get("daily_bars", []))
    return StoredBacktest(
        id=UUID(record.id),
        data_snapshot_id=record.data_snapshot_id,
        request=BacktestRequest(
            symbol=str(config["symbol"]),
            start=datetime.fromisoformat(str(config["start"])).date(),
            end=datetime.fromisoformat(str(config["end"])).date(),
            initial_cash=Decimal(str(config["initial_cash"])),
            short_window=int(str(config["short_window"])),
            long_window=int(str(config["long_window"])),
            strategy_name=str(config.get("strategy_name", record.strategy_name)),
            grid_step_percent=Decimal(str(config.get("grid_step_percent", "0.05"))),
        ),
        daily_bars=[
            DailyBar(
                trade_date=datetime.fromisoformat(str(item["trade_date"])).date(),
                open=Decimal(str(item["open"])),
                high=Decimal(str(item["high"])),
                low=Decimal(str(item["low"])),
                close=Decimal(str(item["close"])),
                volume=Decimal(str(item["volume"])),
            )
            for item in daily_bar_payloads
        ],
        result=BacktestResult(
            metrics=BacktestMetrics(
                total_return=Decimal(str(metrics["total_return"])),
                max_drawdown=Decimal(str(metrics["max_drawdown"])),
                volatility=Decimal(str(metrics["volatility"])),
                trade_count=int(metrics["trade_count"]),
                total_fees=Decimal(str(metrics["total_fees"])),
                annualized_sharpe=Decimal(str(metrics.get("annualized_sharpe", "0"))),
                turnover=Decimal(str(metrics.get("turnover", "0"))),
            ),
            trades=[
                Trade(
                    trade_date=datetime.fromisoformat(str(item["trade_date"])).date(),
                    side=str(item["side"]),
                    price=Decimal(str(item["price"])),
                    quantity=int(item["quantity"]),
                    fee=Decimal(str(item["fee"])),
                )
                for item in record.trades
            ],
            equity_curve=[
                EquityPoint(
                    trade_date=datetime.fromisoformat(str(item["trade_date"])).date(),
                    equity=Decimal(str(item["equity"])),
                )
                for item in record.equity_curve
            ],
        ),
        strategy_name=record.strategy_name,
        strategy_version=str(config.get("strategy_version", record.strategy_version)),
    )
