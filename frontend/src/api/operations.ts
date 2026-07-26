export interface OperationsStatus {
  database: string;
  task_execution_mode: string;
  market_data_provider: string;
  backtest_market_data: string;
  latest_calendar_date: string | null;
  pending_backtest_job_count: number;
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function fetchOperationsStatus(): Promise<OperationsStatus> {
  const response = await fetch(`${apiBaseUrl}/operations/status`);
  if (!response.ok) throw new Error(`Operations status request failed: ${response.status}`);
  return (await response.json()) as OperationsStatus;
}
