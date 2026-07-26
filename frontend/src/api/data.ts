export interface DataSyncStatus {
  status: string;
  source: string | null;
  message: string;
  latest_market_timestamp: string | null;
  latest_observed_at: string | null;
  granularity: string;
}

export interface DataImportResult {
  job_id: number;
  task_id: string;
  status: string;
  symbol?: string | null;
}

export interface DataAvailability {
  symbol: string;
  start: string;
  end: string;
  bar_count: number;
  is_available: boolean;
}

export interface ImportedInstrument {
  symbol: string;
  name: string;
  board: string;
  bar_count: number;
  latest_trade_date: string;
}

export interface DailyBar {
  trade_date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export async function fetchDataSyncStatus(): Promise<DataSyncStatus> {
  const response = await fetch(`${apiBaseUrl}/data/sync-status`);
  if (!response.ok) {
    throw new Error(`Data sync status request failed: ${response.status}`);
  }
  return (await response.json()) as DataSyncStatus;
}

export async function importDailyBars(
  symbol: string,
  start: string,
  end: string,
): Promise<DataImportResult> {
  const response = await fetch(`${apiBaseUrl}/data/imports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols: [symbol], start, end }),
  });
  if (!response.ok) {
    throw new Error(`Data import request failed: ${response.status}`);
  }
  return (await response.json()) as DataImportResult;
}

export async function fetchDataAvailability(
  symbol: string,
  start: string,
  end: string,
): Promise<DataAvailability> {
  const parameters = new URLSearchParams({ symbol, start, end });
  const response = await fetch(`${apiBaseUrl}/data/availability?${parameters}`);
  if (!response.ok) throw new Error(`Data availability request failed: ${response.status}`);
  return (await response.json()) as DataAvailability;
}

export async function importFullHistory(symbol: string): Promise<DataImportResult> {
  const response = await fetch(`${apiBaseUrl}/data/imports/full-history`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol }),
  });
  if (!response.ok) throw new Error(`Full history import failed: ${response.status}`);
  return (await response.json()) as DataImportResult;
}

export async function fetchImportedInstruments(): Promise<ImportedInstrument[]> {
  const response = await fetch(`${apiBaseUrl}/data/instruments`);
  if (!response.ok) throw new Error(`Load instruments failed: ${response.status}`);
  return (await response.json()) as ImportedInstrument[];
}

export async function fetchDailyBars(
  symbol: string,
  limit = 240,
  end?: string,
  after?: string,
): Promise<DailyBar[]> {
  const parameters = new URLSearchParams({ symbol, limit: String(limit) });
  if (end) parameters.set("end", end);
  if (after) parameters.set("after", after);
  const response = await fetch(`${apiBaseUrl}/data/daily-bars?${parameters}`);
  if (!response.ok) throw new Error(`Load daily bars failed: ${response.status}`);
  return (await response.json()) as DailyBar[];
}

export async function deleteImportedInstrument(symbol: string): Promise<{ deleted_bar_count: number }> {
  const response = await fetch(`${apiBaseUrl}/data/instruments/${encodeURIComponent(symbol)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error(`Delete imported data failed: ${response.status}`);
  return (await response.json()) as { deleted_bar_count: number };
}
