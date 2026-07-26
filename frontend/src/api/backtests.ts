export interface BacktestResult {
  id: string;
  status: string;
  strategy: string;
  strategy_version: string;
  data_snapshot_id: string;
  data_source: string;
  adjustment_mode: string;
  fee_model: string;
  data_granularity: string;
  execution_assumption: string;
  symbol: string;
  start: string;
  end: string;
  daily_bars: Array<{
    trade_date: string;
    open: string;
    high: string;
    low: string;
    close: string;
    volume: string;
  }>;
  metrics: {
    total_return: string;
    max_drawdown: string;
    volatility: string;
    trade_count: number;
    total_fees: string;
    annualized_sharpe: string;
    turnover: string;
  };
  trades: Array<{
    trade_date: string;
    side: string;
    price: string;
    quantity: number;
    fee: string;
  }>;
  equity_curve: Array<{
    trade_date: string;
    equity: string;
  }>;
}

export interface BacktestRequest {
  strategyName: string;
  symbol: string;
  start: string;
  end: string;
  initialCash: string;
  shortWindow: number;
  longWindow: number;
  gridStepPercent: string;
}

export interface BacktestJobResult {
  id: string;
  status: string;
  run_id: string | null;
  error_message: string | null;
}

export interface BacktestHistoryJob extends BacktestJobResult {
  symbol: string;
  start: string;
  end: string;
  strategy_name: string;
  initial_cash: string;
  short_window: number;
  long_window: number;
  created_at: string;
  finished_at: string | null;
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function runBacktest(request: BacktestRequest): Promise<BacktestResult> {
  const response = await fetch(`${apiBaseUrl}/backtests`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      strategy_name: request.strategyName,
      symbol: request.symbol,
      start: request.start,
      end: request.end,
      initial_cash: request.initialCash,
      short_window: request.shortWindow,
      long_window: request.longWindow,
      grid_step_percent: request.gridStepPercent,
    }),
  });
  if (!response.ok) {
    throw new Error(`Backtest request failed: ${response.status}`);
  }
  return (await response.json()) as BacktestResult;
}

export async function createBacktestJob(request: BacktestRequest): Promise<BacktestJobResult> {
  const response = await fetch(`${apiBaseUrl}/backtests/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      strategy_name: request.strategyName,
      symbol: request.symbol,
      start: request.start,
      end: request.end,
      initial_cash: request.initialCash,
      short_window: request.shortWindow,
      long_window: request.longWindow,
      grid_step_percent: request.gridStepPercent,
    }),
  });
  if (!response.ok) {
    throw new Error(`Backtest task request failed: ${response.status}`);
  }
  return (await response.json()) as BacktestJobResult;
}

export async function fetchBacktestJob(jobId: string): Promise<BacktestJobResult> {
  const response = await fetch(`${apiBaseUrl}/backtests/jobs/${jobId}`);
  if (!response.ok) {
    throw new Error(`Backtest task lookup failed: ${response.status}`);
  }
  return (await response.json()) as BacktestJobResult;
}

export async function fetchBacktestJobs(limit = 50): Promise<BacktestHistoryJob[]> {
  const response = await fetch(`${apiBaseUrl}/backtests/jobs?limit=${limit}`);
  if (!response.ok) {
    throw new Error(`Backtest history request failed: ${response.status}`);
  }
  return (await response.json()) as BacktestHistoryJob[];
}

export async function fetchBacktest(runId: string): Promise<BacktestResult> {
  const response = await fetch(`${apiBaseUrl}/backtests/${runId}`);
  if (!response.ok) {
    throw new Error(`Backtest result lookup failed: ${response.status}`);
  }
  return (await response.json()) as BacktestResult;
}

export async function cancelBacktestJob(jobId: string): Promise<BacktestJobResult> {
  const response = await fetch(`${apiBaseUrl}/backtests/jobs/${jobId}/cancel`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Backtest task cancellation failed: ${response.status}`);
  }
  return (await response.json()) as BacktestJobResult;
}

export async function deleteBacktestJob(jobId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/backtests/jobs/${jobId}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`Backtest history deletion failed: ${response.status}`);
  }
}
