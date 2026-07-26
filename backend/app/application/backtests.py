from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from app.domain.backtest import (
    BacktestResult,
    DailyBar,
    run_buy_and_hold_backtest,
    run_grid_backtest,
    run_moving_average_backtest,
)
from app.domain.trading_rules import Exchange
from app.providers.fixture_provider import FixtureMarketDataProvider


@dataclass(frozen=True)
class BacktestRequest:
    symbol: str
    start: date
    end: date
    initial_cash: Decimal
    short_window: int
    long_window: int
    strategy_name: str = "moving_average_cross"
    grid_step_percent: Decimal = Decimal("0.05")


@dataclass(frozen=True)
class StoredBacktest:
    id: UUID
    request: BacktestRequest
    daily_bars: list[DailyBar]
    result: BacktestResult
    data_snapshot_id: str
    strategy_name: str
    strategy_version: str


class BacktestRepository(Protocol):
    def save(self, run: StoredBacktest) -> None: ...

    def get(self, run_id: UUID) -> StoredBacktest | None: ...


class BacktestMarketDataReader(Protocol):
    def read_daily_bars(
        self, symbol: str, start: date, end: date
    ) -> tuple[list[DailyBar], str]: ...


class InMemoryBacktestRepository:
    def __init__(self) -> None:
        self._runs: dict[UUID, StoredBacktest] = {}

    def save(self, run: StoredBacktest) -> None:
        self._runs[run.id] = run

    def get(self, run_id: UUID) -> StoredBacktest | None:
        return self._runs.get(run_id)


class BacktestService:
    """Runs controlled, versioned daily strategies against a declared data snapshot."""

    def __init__(
        self,
        fixture_path: Path,
        repository: BacktestRepository | None = None,
        market_data_reader: BacktestMarketDataReader | None = None,
    ) -> None:
        self._provider = FixtureMarketDataProvider(fixture_path)
        self._repository = repository or InMemoryBacktestRepository()
        self._market_data_reader = market_data_reader

    def list_strategies(self) -> list[dict[str, object]]:
        return [
            {
                "name": "moving_average_cross",
                "version": "1.0.0",
                "description": "双均线交叉：收盘生成信号，下一交易日开盘模拟成交。",
                "parameters": {"short_window": 3, "long_window": 5},
            },
            {
                "name": "buy_and_hold",
                "version": "1.0.0",
                "description": "基准策略：首个可用交易日开盘买入并持有至样本结束。",
                "parameters": {},
            },
            {
                "name": "grid",
                "version": "1.0.0",
                "description": "日线长仓网格策略",
                "parameters": {"grid_step_percent": 5},
            },
        ]

    def create_moving_average_run(self, request: BacktestRequest) -> StoredBacktest:
        bars, data_snapshot_id = self._load_bars(request)
        result = self._run_strategy(request, bars)
        run = StoredBacktest(
            id=uuid4(),
            request=request,
            daily_bars=bars,
            result=result,
            data_snapshot_id=data_snapshot_id,
            strategy_name=request.strategy_name,
            strategy_version=_strategy_version(request.strategy_name),
        )
        self._repository.save(run)
        return run

    def get_run(self, run_id: UUID) -> StoredBacktest | None:
        return self._repository.get(run_id)

    def _load_bars(self, request: BacktestRequest) -> tuple[list[DailyBar], str]:
        if self._market_data_reader is not None:
            return self._market_data_reader.read_daily_bars(
                request.symbol, request.start, request.end
            )
        raw_bars = self._provider.fetch_daily_bars([request.symbol], request.start, request.end)
        bars = [
            DailyBar(
                trade_date=bar.trade_date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in raw_bars
        ]
        return bars, "fixture:daily-bars:v1"

    @staticmethod
    def _run_strategy(request: BacktestRequest, bars: list[DailyBar]) -> BacktestResult:
        if request.strategy_name == "moving_average_cross":
            return run_moving_average_backtest(
                bars=bars,
                initial_cash=request.initial_cash,
                short_window=request.short_window,
                long_window=request.long_window,
                exchange=Exchange.SSE,
            )
        if request.strategy_name == "buy_and_hold":
            return run_buy_and_hold_backtest(
                bars=bars,
                initial_cash=request.initial_cash,
                exchange=Exchange.SSE,
            )
        if request.strategy_name == "grid":
            return run_grid_backtest(
                bars=bars,
                initial_cash=request.initial_cash,
                grid_step_percent=request.grid_step_percent,
                exchange=Exchange.SSE,
            )
        raise ValueError("UNSUPPORTED_STRATEGY")


def _strategy_version(strategy_name: str) -> str:
    if strategy_name in {"moving_average_cross", "buy_and_hold", "grid"}:
        return "1.0.0"
    raise ValueError("UNSUPPORTED_STRATEGY")
