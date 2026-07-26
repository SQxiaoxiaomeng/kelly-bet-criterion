const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

export interface SimAccount {
  id: string;
  name: string;
  status: string;
  cash: string;
  frozen_cash: string;
  created_at: string;
  can_delete: boolean;
}

export interface SimOrder {
  id: string;
  account_id: string;
  side: string;
  quantity: number;
  filled_quantity: number;
  limit_price: string;
  status: string;
  rejection_reason: string | null;
}

export interface SimPosition {
  symbol: string;
  quantity: number;
  available_quantity: number;
  frozen_quantity: number;
  average_cost: string;
}

export interface RiskEvent {
  id: string;
  order_id: string | null;
  rule_code: string;
  decision: string;
  detail: string;
}

export interface AuditEvent {
  id: string;
  category: string;
  action: string;
  reference_id: string;
  detail: Record<string, string | number>;
}

export interface SimFill {
  id: string;
  order_id: string;
  price: string;
  quantity: number;
  fee: string;
  filled_at: string;
}

export interface CashLedgerEntry {
  id: string;
  amount: string;
  reason: string;
  reference_id: string;
  created_at: string;
}

export interface AccountSnapshot {
  as_of_date: string;
  cash: string;
  frozen_cash: string;
  market_value: string;
  equity: string;
}

export interface CorporateActionApplication {
  corporate_action_id: string;
  action_type: string;
  ex_date: string;
  amount: string;
  applied_at: string;
}

export async function createSimAccount(name: string, initialCash: string): Promise<SimAccount> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, initial_cash: initialCash }),
  });
  if (!response.ok) throw new Error(`Create account failed: ${response.status}`);
  return (await response.json()) as SimAccount;
}

export async function fetchSimAccount(accountId: string): Promise<SimAccount> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}`);
  if (!response.ok) throw new Error(`Load account failed: ${response.status}`);
  return (await response.json()) as SimAccount;
}

export async function fetchSimAccounts(): Promise<SimAccount[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts`);
  if (!response.ok) throw new Error(`Load accounts failed: ${response.status}`);
  return (await response.json()) as SimAccount[];
}

export async function updateSimAccount(
  accountId: string, update: { name?: string; status?: "ACTIVE" | "ARCHIVED" },
): Promise<SimAccount> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!response.ok) throw new Error(`Update account failed: ${response.status}`);
  return (await response.json()) as SimAccount;
}

export async function deleteSimAccount(accountId: string): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`Delete account failed: ${response.status}`);
}

export async function submitSimOrder(
  accountId: string, symbol: string, side: string, quantity: number, limitPrice: string,
): Promise<SimOrder> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ symbol, side, quantity, limit_price: limitPrice }),
  });
  if (!response.ok) throw new Error(`Submit order failed: ${response.status}`);
  return (await response.json()) as SimOrder;
}

export async function fetchSimOrders(accountId: string): Promise<SimOrder[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/orders`);
  if (!response.ok) throw new Error(`Load orders failed: ${response.status}`);
  return (await response.json()) as SimOrder[];
}

export async function fetchSimPositions(accountId: string): Promise<SimPosition[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/positions`);
  if (!response.ok) throw new Error(`Load positions failed: ${response.status}`);
  return (await response.json()) as SimPosition[];
}

export async function cancelSimOrder(accountId: string, orderId: string): Promise<SimOrder> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/orders/${orderId}/cancel`, {
    method: "POST",
  });
  if (!response.ok) throw new Error(`Cancel order failed: ${response.status}`);
  return (await response.json()) as SimOrder;
}

export async function settleSimAccount(accountId: string): Promise<number> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/settle`, { method: "POST" });
  if (!response.ok) throw new Error(`Settlement failed: ${response.status}`);
  const result = (await response.json()) as { expired_order_count: number };
  return result.expired_order_count;
}

export async function fetchRiskEvents(accountId: string): Promise<RiskEvent[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/risk-events`);
  if (!response.ok) throw new Error(`Load risk events failed: ${response.status}`);
  return (await response.json()) as RiskEvent[];
}

export async function fetchAuditEvents(accountId: string): Promise<AuditEvent[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/audit-events`);
  if (!response.ok) throw new Error(`Load audit events failed: ${response.status}`);
  return (await response.json()) as AuditEvent[];
}

export async function fetchSimFills(accountId: string): Promise<SimFill[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/fills`);
  if (!response.ok) throw new Error(`Load fills failed: ${response.status}`);
  return (await response.json()) as SimFill[];
}

export async function fetchCashLedger(accountId: string): Promise<CashLedgerEntry[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/cash-ledger`);
  if (!response.ok) throw new Error(`Load cash ledger failed: ${response.status}`);
  return (await response.json()) as CashLedgerEntry[];
}

export async function fetchAccountSnapshots(accountId: string): Promise<AccountSnapshot[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/snapshots`);
  if (!response.ok) throw new Error(`Load account snapshots failed: ${response.status}`);
  return (await response.json()) as AccountSnapshot[];
}

export async function fetchCorporateActionApplications(
  accountId: string,
): Promise<CorporateActionApplication[]> {
  const response = await fetch(`${apiBaseUrl}/sim/accounts/${accountId}/corporate-action-applications`);
  if (!response.ok) throw new Error(`Load corporate actions failed: ${response.status}`);
  return (await response.json()) as CorporateActionApplication[];
}
