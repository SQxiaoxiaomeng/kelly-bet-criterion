import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  cancelBacktestJob,
  createBacktestJob,
  deleteBacktestJob,
  fetchBacktest,
  fetchBacktestJob,
  fetchBacktestJobs,
  type BacktestHistoryJob,
  type BacktestJobResult,
  type BacktestResult,
} from "./api/backtests";
import {
  fetchDataAvailability,
  deleteImportedInstrument,
  fetchDailyBars,
  fetchImportedInstruments,
  importFullHistory,
  type DataImportResult,
  type DataAvailability,
  type DailyBar,
  type ImportedInstrument,
} from "./api/data";
import { CandlestickChart } from "./components/CandlestickChart";
import {
  cancelSimOrder,
  createSimAccount,
  deleteSimAccount,
  fetchSimOrders,
  fetchSimPositions,
  fetchRiskEvents,
  fetchAuditEvents,
  fetchSimAccount,
  fetchSimAccounts,
  fetchAccountSnapshots,
  fetchCashLedger,
  fetchCorporateActionApplications,
  fetchSimFills,
  settleSimAccount,
  submitSimOrder,
  updateSimAccount,
  type SimAccount,
  type SimOrder,
  type SimPosition,
  type RiskEvent,
  type AuditEvent,
  type AccountSnapshot,
  type CashLedgerEntry,
  type CorporateActionApplication,
  type SimFill,
} from "./api/sim";
import "./styles.css";

type ActiveTab = "market" | "backtest" | "simulation";

function toDateInputValue(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function recentThreeMonthRange() {
  const end = new Date();
  const start = new Date(end);
  start.setMonth(start.getMonth() - 3);
  return { start: toDateInputValue(start), end: toDateInputValue(end) };
}

function normalizeAshareSymbol(value: string) {
  const normalized = value.trim().toUpperCase();
  if (!/^\d{6}$/.test(normalized)) return normalized;
  return normalized.startsWith("6") ? `SSE:${normalized}` : `SZSE:${normalized}`;
}

export function App() {
  const [importResult, setImportResult] = useState<DataImportResult>();
  const [instruments, setInstruments] = useState<ImportedInstrument[]>([]);
  const [selectedInstrument, setSelectedInstrument] = useState<string>();
  const [dailyBars, setDailyBars] = useState<DailyBar[]>([]);
  const dailyBarsRef = useRef<DailyBar[]>([]);
  const isDailyNavigationInProgress = useRef(false);
  const [latestDailyBarDate, setLatestDailyBarDate] = useState<string>();
  const [instrumentSearch, setInstrumentSearch] = useState("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("market");
  const [dataAvailability, setDataAvailability] = useState<DataAvailability>();
  const [backtest, setBacktest] = useState<BacktestResult>();
  const [backtestJob, setBacktestJob] = useState<BacktestJobResult>();
  const [backtestHistory, setBacktestHistory] = useState<BacktestHistoryJob[]>([]);
  const [backtestSymbol, setBacktestSymbol] = useState("");
  const [marketStockCode, setMarketStockCode] = useState("");
  const [strategyName, setStrategyName] = useState("moving_average_cross");
  const [start, setStart] = useState(() => recentThreeMonthRange().start);
  const [end, setEnd] = useState(() => recentThreeMonthRange().end);
  const [initialCash, setInitialCash] = useState("100000");
  const [shortWindow, setShortWindow] = useState("3");
  const [longWindow, setLongWindow] = useState("5");
  const [gridStepPercent, setGridStepPercent] = useState("5");
  const [isImporting, setIsImporting] = useState(false);
  const [updatingInstrumentSymbol, setUpdatingInstrumentSymbol] = useState<string>();
  const [isRunningBacktest, setIsRunningBacktest] = useState(false);
  const [error, setError] = useState<string>();
  const [simAccount, setSimAccount] = useState<SimAccount>();
  const [simAccounts, setSimAccounts] = useState<SimAccount[]>([]);
  const [simOrders, setSimOrders] = useState<SimOrder[]>([]);
  const [simPositions, setSimPositions] = useState<SimPosition[]>([]);
  const [riskEvents, setRiskEvents] = useState<RiskEvent[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [simFills, setSimFills] = useState<SimFill[]>([]);
  const [cashLedger, setCashLedger] = useState<CashLedgerEntry[]>([]);
  const [accountSnapshots, setAccountSnapshots] = useState<AccountSnapshot[]>([]);
  const [corporateActionApplications, setCorporateActionApplications] = useState<CorporateActionApplication[]>([]);
  const [simInitialCash, setSimInitialCash] = useState("");
  const [simAccountName, setSimAccountName] = useState("");
  const [isAccountManagerOpen, setIsAccountManagerOpen] = useState(false);
  const [editingSimAccountId, setEditingSimAccountId] = useState<string>();
  const [editingSimAccountName, setEditingSimAccountName] = useState("");
  const [simSymbol, setSimSymbol] = useState("");
  const [simLatestBar, setSimLatestBar] = useState<DailyBar>();
  const [isLoadingSimQuote, setIsLoadingSimQuote] = useState(false);
  const [simPrice, setSimPrice] = useState("");
  const [simQuantity, setSimQuantity] = useState("100");
  const simAccountId = simAccount?.id;
  function setDisplayedDailyBars(bars: DailyBar[]) {
    dailyBarsRef.current = bars;
    setDailyBars(bars);
  }
  const visibleInstruments = useMemo(() => {
    const query = instrumentSearch.trim().toLowerCase();
    return [...instruments]
      .filter((item) => !query || `${item.symbol} ${item.name}`.toLowerCase().includes(query))
      .sort((left, right) => left.symbol.localeCompare(right.symbol));
  }, [instrumentSearch, instruments]);
  const selectedInstrumentName = useMemo(
    () => instruments.find((instrument) => instrument.symbol === selectedInstrument)?.name
      ?? selectedInstrument?.replace(/^[^:]+:/, ""),
    [instruments, selectedInstrument],
  );
  const selectedInstrumentDetails = useMemo(
    () => instruments.find((instrument) => instrument.symbol === selectedInstrument),
    [instruments, selectedInstrument],
  );
  const selectedSimInstrument = useMemo(
    () => instruments.find((instrument) => instrument.symbol === simSymbol),
    [instruments, simSymbol],
  );
  const normalizedBacktestSymbol = useMemo(
    () => normalizeAshareSymbol(backtestSymbol),
    [backtestSymbol],
  );
  const latestDailyBar = dailyBars.at(-1);
  const previousDailyBar = dailyBars.at(-2);
  const latestChangePercent = latestDailyBar && previousDailyBar
    ? ((Number(latestDailyBar.close) - Number(previousDailyBar.close)) / Number(previousDailyBar.close)) * 100
    : undefined;
  const formatInstrumentLabel = (instrument: ImportedInstrument) => {
    const code = instrument.symbol.replace(/^[^:]+:/, "");
    return instrument.name === code ? code : `${instrument.name}（${code}）`;
  };

  useEffect(() => {
    void fetchImportedInstruments().then(setInstruments).catch(showConnectionError);
    void fetchBacktestJobs().then(setBacktestHistory).catch(showConnectionError);
    void fetchSimAccounts().then(async (accounts) => {
      setSimAccounts(accounts);
      const defaultAccount = accounts.find((account) => account.status === "ACTIVE") ?? accounts[0];
      if (defaultAccount) await refreshSimAccountState(defaultAccount.id);
    }).catch(showConnectionError);
  }, []);

  useEffect(() => {
    if (selectedInstrument || instruments.length === 0) return;
    const firstInstrument = [...instruments].sort((left, right) => left.symbol.localeCompare(right.symbol))[0];
    setSelectedInstrument(firstInstrument.symbol);
  }, [instruments, selectedInstrument]);

  useEffect(() => {
    if (!normalizedBacktestSymbol || !start || !end || start > end) {
      setDataAvailability(undefined);
      return;
    }
    void fetchDataAvailability(normalizedBacktestSymbol, start, end).then(setDataAvailability).catch(showConnectionError);
  }, [normalizedBacktestSymbol, start, end]);

  useEffect(() => {
    if (!selectedInstrument) {
      setDisplayedDailyBars([]);
      return;
    }
    void fetchDailyBars(selectedInstrument).then((bars) => {
      setDisplayedDailyBars(bars);
      setLatestDailyBarDate(bars.at(-1)?.trade_date);
    }).catch(showConnectionError);
  }, [selectedInstrument]);

  useEffect(() => {
    if (!simSymbol) {
      setSimLatestBar(undefined);
      setSimPrice("");
      return;
    }
    setIsLoadingSimQuote(true);
    let isCurrentRequest = true;
    void fetchDailyBars(simSymbol, 1).then((bars) => {
      if (!isCurrentRequest) return;
      const latestBar = bars.at(-1);
      setSimLatestBar(latestBar);
      setSimPrice(latestBar?.close ?? "");
    }).catch((reason: unknown) => {
      if (isCurrentRequest) showConnectionError(reason);
    }).finally(() => {
      if (isCurrentRequest) setIsLoadingSimQuote(false);
    });
    return () => { isCurrentRequest = false; };
  }, [simSymbol]);

  useEffect(() => {
    if (!simAccountId) return;
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
    const streamUrl = `${apiBaseUrl.replace(/^http/, "ws")}/sim/accounts/${simAccountId}/stream`;
    const socket = new WebSocket(streamUrl);
    socket.onmessage = () => void refreshSimAccountState(simAccountId);
    return () => socket.close();
  }, [simAccountId]);

  function showConnectionError(reason: unknown) {
    setError(reason instanceof Error ? reason.message : "无法连接后端服务。");
  }

  async function handleFullHistoryImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsImporting(true);
    setError(undefined);
    setBacktest(undefined);
    try {
      const result = await importFullHistory(marketStockCode);
      setImportResult(result);
      const imported = await fetchImportedInstruments();
      setInstruments(imported);
      if (result.symbol) setSelectedInstrument(result.symbol);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "行情导入失败。");
    } finally {
      setIsImporting(false);
    }
  }

  async function handleDeleteImportedInstrument(instrument: ImportedInstrument) {
    if (!window.confirm(`删除 ${instrument.symbol} 已导入的 ${instrument.bar_count} 根日线数据？`)) return;
    setError(undefined);
    try {
      await deleteImportedInstrument(instrument.symbol);
      setInstruments(await fetchImportedInstruments());
      if (selectedInstrument === instrument.symbol) setSelectedInstrument(undefined);
      if (simSymbol === instrument.symbol) setSimSymbol("");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "删除已导入行情失败。");
    }
  }

  async function handleUpdateImportedInstrument(instrument: ImportedInstrument) {
    setUpdatingInstrumentSymbol(instrument.symbol);
    setError(undefined);
    try {
      const result = await importFullHistory(instrument.symbol);
      setImportResult(result);
      setInstruments(await fetchImportedInstruments());
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "更新日线行情失败。");
    } finally {
      setUpdatingInstrumentSymbol(undefined);
    }
  }

  async function showOlderDailyBars() {
    if (isDailyNavigationInProgress.current) return;
    const currentBars = dailyBarsRef.current;
    if (!selectedInstrument || currentBars.length === 0) return;
    isDailyNavigationInProgress.current = true;
    // 以当前窗口的最后一根 K 线为锚点回退一天。后端会取该日期
    // 之前的最近 240 根数据，因此新旧窗口重叠 239 根，只左移一根。
    const latest = currentBars.at(-1)?.trade_date;
    if (!latest) return;
    const previousDay = new Date(`${latest}T00:00:00Z`);
    previousDay.setUTCDate(previousDay.getUTCDate() - 1);
    const end = previousDay.toISOString().slice(0, 10);
    try {
      const olderBars = await fetchDailyBars(selectedInstrument, 240, end);
      if (olderBars.length === 0) return;
      if (olderBars.at(-1)?.trade_date === currentBars.at(-1)?.trade_date) return;
      setDisplayedDailyBars(olderBars);
    } catch (reason: unknown) {
      showConnectionError(reason);
    } finally {
      isDailyNavigationInProgress.current = false;
    }
  }

  async function showNewerDailyBars() {
    if (isDailyNavigationInProgress.current) return;
    const currentBars = dailyBarsRef.current;
    if (!selectedInstrument || !latestDailyBarDate || currentBars.length === 0) return;
    const latest = currentBars.at(-1)?.trade_date;
    if (!latest || latest >= latestDailyBarDate) return;
    isDailyNavigationInProgress.current = true;
    try {
      const newerBars = await fetchDailyBars(selectedInstrument, 240, undefined, latest);
      if (newerBars.at(-1)?.trade_date === latest) return;
      setDisplayedDailyBars(newerBars);
    } catch (reason: unknown) {
      showConnectionError(reason);
    } finally {
      isDailyNavigationInProgress.current = false;
    }
  }

  async function handleRunBacktest() {
    setIsRunningBacktest(true);
    setError(undefined);
    try {
      const request = {
        strategyName,
        symbol: normalizedBacktestSymbol,
        start,
        end,
        initialCash,
        shortWindow: Number(shortWindow),
        longWindow: Number(longWindow),
        gridStepPercent: String(Number(gridStepPercent) / 100),
      };
      const job = await createBacktestJob(request);
      setBacktestJob(job);
      await resolveBacktestJob(job);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "回测运行失败。");
    } finally {
      setIsRunningBacktest(false);
      void refreshBacktestHistory();
    }
  }

  async function refreshBacktestHistory() {
    try {
      setBacktestHistory(await fetchBacktestJobs());
    } catch (reason: unknown) {
      showConnectionError(reason);
    }
  }

  async function resolveBacktestJob(initialJob: BacktestJobResult) {
    let job = initialJob;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      if (job.status === "COMPLETED" && job.run_id) {
        setBacktest(await fetchBacktest(job.run_id));
        return;
      }
      if (["FAILED", "CANCELLED"].includes(job.status)) {
        throw new Error(job.error_message ?? `Backtest job ${job.status}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
      job = await fetchBacktestJob(job.id);
      setBacktestJob(job);
    }
    throw new Error("Backtest job timed out while waiting for completion");
  }

  async function handleCancelBacktest() {
    if (!backtestJob || !["PENDING", "RUNNING"].includes(backtestJob.status)) return;
    setError(undefined);
    try {
      setBacktestJob(await cancelBacktestJob(backtestJob.id));
      await refreshBacktestHistory();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "取消回测任务失败。");
    }
  }

  function restoreBacktestParameters(job: BacktestHistoryJob) {
    setBacktestSymbol(job.symbol.replace(/^[^:]+:/, ""));
    setStart(job.start);
    setEnd(job.end);
    setStrategyName(job.strategy_name);
    setInitialCash(job.initial_cash);
    setShortWindow(String(job.short_window));
    setLongWindow(String(job.long_window));
  }

  async function handleViewBacktestHistory(job: BacktestHistoryJob) {
    setError(undefined);
    setBacktestJob(job);
    setBacktest(undefined);
    restoreBacktestParameters(job);
    try {
      if (job.run_id) setBacktest(await fetchBacktest(job.run_id));
    } catch (reason: unknown) {
      showConnectionError(reason);
    }
  }

  async function handleDeleteBacktestHistory(job: BacktestHistoryJob) {
    if (!window.confirm(`删除 ${job.symbol} 于 ${job.created_at.slice(0, 16)} 创建的回测任务？`)) return;
    setError(undefined);
    try {
      await deleteBacktestJob(job.id);
      if (backtestJob?.id === job.id) {
        setBacktestJob(undefined);
        setBacktest(undefined);
      }
      await refreshBacktestHistory();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "删除历史回测任务失败。");
    }
  }

  async function handleCreateSimAccount() {
    const name = simAccountName.trim();
    if (!name || Number(simInitialCash) <= 0) {
      setError("请填写账户名称和大于零的初始资金。");
      return;
    }
    setError(undefined);
    try {
      const account = await createSimAccount(name, simInitialCash);
      setSimAccount(account);
      setSimAccounts(await fetchSimAccounts());
      setSimOrders([]);
      setSimPositions([]);
      setRiskEvents([]);
      setAuditEvents([]);
      setSimFills([]);
      setCashLedger([]);
      setAccountSnapshots([]);
      setCorporateActionApplications([]);
      setIsAccountManagerOpen(false);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "创建模拟账户失败。");
    }
  }

  async function refreshSimAccountState(accountId: string) {
    const [account, orders, positions, risks, audits, fills, ledger, snapshots, corporateActions] =
      await Promise.all([
        fetchSimAccount(accountId),
        fetchSimOrders(accountId),
        fetchSimPositions(accountId),
        fetchRiskEvents(accountId),
        fetchAuditEvents(accountId),
        fetchSimFills(accountId),
        fetchCashLedger(accountId),
        fetchAccountSnapshots(accountId),
        fetchCorporateActionApplications(accountId),
      ]);
    setSimAccount(account);
    setSimOrders(orders);
    setSimPositions(positions);
    setRiskEvents(risks);
    setAuditEvents(audits);
    setSimFills(fills);
    setCashLedger(ledger);
    setAccountSnapshots(snapshots);
    setCorporateActionApplications(corporateActions);
  }

  async function handleSelectSimAccount(accountId: string) {
    setError(undefined);
    try {
      await refreshSimAccountState(accountId);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "加载模拟账户失败。");
    }
  }

  async function refreshSimAccounts() {
    setSimAccounts(await fetchSimAccounts());
  }

  async function handleRenameSimAccount(accountId: string) {
    const name = editingSimAccountName.trim();
    if (!name) return;
    setError(undefined);
    try {
      const updated = await updateSimAccount(accountId, { name });
      if (simAccount?.id === accountId) setSimAccount(updated);
      await refreshSimAccounts();
      setEditingSimAccountId(undefined);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "重命名模拟账户失败。");
    }
  }

  async function handleSetSimAccountStatus(account: SimAccount, status: "ACTIVE" | "ARCHIVED") {
    setError(undefined);
    try {
      const updated = await updateSimAccount(account.id, { status });
      if (simAccount?.id === account.id) setSimAccount(updated);
      await refreshSimAccounts();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "更新模拟账户状态失败。");
    }
  }

  async function handleDeleteSimAccount(account: SimAccount) {
    if (!window.confirm(`确认删除空账户“${account.name}”？此操作不可恢复。`)) return;
    setError(undefined);
    try {
      await deleteSimAccount(account.id);
      const accounts = await fetchSimAccounts();
      setSimAccounts(accounts);
      if (simAccount?.id === account.id) {
        const nextAccount = accounts.find((item) => item.status === "ACTIVE") ?? accounts[0];
        if (nextAccount) await refreshSimAccountState(nextAccount.id);
        else setSimAccount(undefined);
      }
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "删除模拟账户失败；有交易记录的账户只能归档。");
    }
  }

  async function handleSimOrder(side: string) {
    if (!simAccount) return;
    if (!simSymbol || !simLatestBar || Number(simPrice) <= 0 || !isSimQuantityValid) {
      setError("请选择已导入且有日线数据的股票，并填写合法的限价和数量。");
      return;
    }
    setError(undefined);
    try {
      await submitSimOrder(simAccount.id, simSymbol, side, Number(simQuantity), simPrice);
      setSimAccount(await fetchSimAccount(simAccount.id));
      setSimOrders(await fetchSimOrders(simAccount.id));
      setSimPositions(await fetchSimPositions(simAccount.id));
      setRiskEvents(await fetchRiskEvents(simAccount.id));
      setAuditEvents(await fetchAuditEvents(simAccount.id));
      setSimFills(await fetchSimFills(simAccount.id));
      setCashLedger(await fetchCashLedger(simAccount.id));
      setAccountSnapshots(await fetchAccountSnapshots(simAccount.id));
      setCorporateActionApplications(await fetchCorporateActionApplications(simAccount.id));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "模拟下单失败。");
    }
  }

  async function handleCancelSimOrder(orderId: string) {
    if (!simAccount) return;
    setError(undefined);
    try {
      await cancelSimOrder(simAccount.id, orderId);
      setSimAccount(await fetchSimAccount(simAccount.id));
      setSimOrders(await fetchSimOrders(simAccount.id));
      setSimPositions(await fetchSimPositions(simAccount.id));
      setRiskEvents(await fetchRiskEvents(simAccount.id));
      setAuditEvents(await fetchAuditEvents(simAccount.id));
      setSimFills(await fetchSimFills(simAccount.id));
      setCashLedger(await fetchCashLedger(simAccount.id));
      setAccountSnapshots(await fetchAccountSnapshots(simAccount.id));
      setCorporateActionApplications(await fetchCorporateActionApplications(simAccount.id));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "撤单失败。");
    }
  }

  async function handleSettlement() {
    if (!simAccount) return;
    setError(undefined);
    try {
      await settleSimAccount(simAccount.id);
      setSimAccount(await fetchSimAccount(simAccount.id));
      setSimOrders(await fetchSimOrders(simAccount.id));
      setSimPositions(await fetchSimPositions(simAccount.id));
      setRiskEvents(await fetchRiskEvents(simAccount.id));
      setAuditEvents(await fetchAuditEvents(simAccount.id));
      setSimFills(await fetchSimFills(simAccount.id));
      setCashLedger(await fetchCashLedger(simAccount.id));
      setAccountSnapshots(await fetchAccountSnapshots(simAccount.id));
      setCorporateActionApplications(await fetchCorporateActionApplications(simAccount.id));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "日终结算失败。");
    }
  }

  const canRunBacktest = dataAvailability?.is_available === true;
  const isSimQuantityValid = Number.isInteger(Number(simQuantity)) && Number(simQuantity) >= 100 && Number(simQuantity) % 100 === 0;
  const isSimAccountActive = simAccount?.status === "ACTIVE";

  return (
    <main className="app-shell">
      <header className="app-header">
        <div><p className="eyebrow">A-SHARE QUANT LAB</p><h1>量化交易工作台</h1></div>
        <p className="app-subtitle">研究、回测与模拟交易</p>
      </header>
      <nav className="tab-list" aria-label="功能页面">
        <button type="button" className={activeTab === "market" ? "active-tab" : ""} onClick={() => setActiveTab("market")}>日线行情</button>
        <button type="button" className={activeTab === "backtest" ? "active-tab" : ""} onClick={() => setActiveTab("backtest")}>日频回测</button>
        <button type="button" className={activeTab === "simulation" ? "active-tab" : ""} onClick={() => setActiveTab("simulation")}>模拟交易</button>
      </nav>
      {error ? <p className="error" role="alert">{error}</p> : null}
      {activeTab === "market" ? <section className="market-workspace" aria-label="日线行情工作台">
        <aside className="watchlist-panel">
          <div className="panel-heading"><div><p className="panel-kicker">WATCHLIST</p><h2>股票池</h2></div><span>{instruments.length}</span></div>
          <form className="quick-import" onSubmit={(event) => void handleFullHistoryImport(event)}>
            <input aria-label="股票代码（6 位）" value={marketStockCode} pattern="[0-9]{6}" maxLength={6} placeholder="600000" onChange={(event) => setMarketStockCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required />
            <button type="submit" disabled={isImporting}>{isImporting ? "同步中" : "添加"}</button>
          </form>
          {importResult ? <p className="import-result">同步任务 #{importResult.job_id}：{importResult.status}</p> : null}
          <div className="instrument-toolbar">
            <input aria-label="搜索已导入股票" placeholder="搜索名称或代码" value={instrumentSearch} onChange={(event) => setInstrumentSearch(event.target.value)} />
          </div>
          {instruments.length === 0 ? <p className="empty-watchlist">输入股票代码，导入全量历史日线后开始研究。</p> : (
            <ul className="watchlist">
              {visibleInstruments.map((instrument) => <li key={instrument.symbol} className={selectedInstrument === instrument.symbol ? "selected-instrument" : ""}>
                <button type="button" className="instrument-select" onClick={() => setSelectedInstrument(instrument.symbol)}><strong>{formatInstrumentLabel(instrument)}</strong><span>{instrument.latest_trade_date}</span></button>
                <button type="button" className="update-instrument" disabled={updatingInstrumentSymbol === instrument.symbol} aria-label={`更新 ${instrument.name} 的日线数据`} title="增量更新日线数据" onClick={() => void handleUpdateImportedInstrument(instrument)}>{updatingInstrumentSymbol === instrument.symbol ? "更新中" : "更新"}</button>
                <button type="button" className="delete-instrument" aria-label={`删除 ${instrument.name}`} onClick={() => void handleDeleteImportedInstrument(instrument)}>×</button>
              </li>)}
            </ul>
          )}
        </aside>
        <section className="chart-panel" aria-labelledby="daily-chart">
          {selectedInstrument ? <>
            <header className="quote-header"><div><p>{selectedInstrument.replace(/^[^:]+:/, "")}</p><h2 id="daily-chart">{selectedInstrumentName}</h2></div><div className="headline-quote"><strong className={latestChangePercent === undefined ? "" : latestChangePercent >= 0 ? "price-up" : "price-down"}>{latestDailyBar?.close ?? "--"}</strong><span className={latestChangePercent === undefined ? "" : latestChangePercent >= 0 ? "price-up" : "price-down"}>{latestChangePercent === undefined ? "--" : `${latestChangePercent >= 0 ? "+" : ""}${latestChangePercent.toFixed(2)}%`}</span></div></header>
            <CandlestickChart bars={dailyBars} onOlder={() => void showOlderDailyBars()} onNewer={() => void showNewerDailyBars()} canShowOlder={dailyBars.length === 240} canShowNewer={dailyBars.at(-1)?.trade_date !== latestDailyBarDate} />
          </> : <div className="chart-empty"><h2>选择一只股票</h2><p>从左侧股票池选择证券，查看日线行情。</p></div>}
        </section>
        <aside className="market-summary">
          <p className="panel-kicker">MARKET SUMMARY</p><h2>行情摘要</h2>
          {selectedInstrument && selectedInstrumentDetails ? <dl className="summary-list">
            <dt>最新交易日</dt><dd>{latestDailyBar?.trade_date ?? selectedInstrumentDetails.latest_trade_date}</dd>
            <dt>开</dt><dd>{latestDailyBar?.open ?? "--"}</dd>
            <dt>高</dt><dd>{latestDailyBar?.high ?? "--"}</dd>
            <dt>低</dt><dd>{latestDailyBar?.low ?? "--"}</dd>
            <dt>收</dt><dd>{latestDailyBar?.close ?? "--"}</dd>
            <dt>涨跌幅</dt><dd className={latestChangePercent === undefined ? "" : latestChangePercent >= 0 ? "price-up" : "price-down"}>{latestChangePercent === undefined ? "--" : `${latestChangePercent >= 0 ? "+" : ""}${latestChangePercent.toFixed(2)}%`}</dd>
          </dl> : <p className="summary-empty">尚未选择股票。</p>}
        </aside>
      </section> : null}
      {activeTab === "backtest" ? <section className="backtest-workspace" aria-labelledby="backtest">
        <header className="backtest-header"><div><p className="panel-kicker">DAILY BACKTEST</p><h2 id="backtest">日频回测</h2><p>收盘生成信号，于下一交易日开盘模拟成交。</p></div><span>模拟研究</span></header>
        <div className="backtest-layout">
          <div className="backtest-config">
            <div className="config-group"><h3>标的与周期</h3><div className="config-grid"><label>证券代码<input value={backtestSymbol} pattern="[0-9]{6}" maxLength={6} placeholder="600000" onChange={(event) => setBacktestSymbol(event.target.value.replace(/\D/g, "").slice(0, 6))} required /></label><label>开始日期<input type="date" value={start} onChange={(event) => setStart(event.target.value)} required /></label><label>结束日期<input type="date" value={end} onChange={(event) => setEnd(event.target.value)} required /></label></div></div>
            <div className="config-group"><h3>策略与资金</h3><div className="config-grid"><label>策略<select value={strategyName} onChange={(event) => setStrategyName(event.target.value)}><option value="moving_average_cross">双均线交叉（3 / 5）</option><option value="grid">日线网格（5%）</option><option value="buy_and_hold">买入并持有基准</option></select></label><label>初始资金（元）<input type="number" min="1" step="1" value={initialCash} onChange={(event) => setInitialCash(event.target.value)} required /></label>{strategyName === "moving_average_cross" ? <><label>短期均线窗口<input type="number" min="1" value={shortWindow} onChange={(event) => setShortWindow(event.target.value)} required /></label><label>长期均线窗口<input type="number" min="2" value={longWindow} onChange={(event) => setLongWindow(event.target.value)} required /></label></> : null}{strategyName === "grid" ? <label>网格间距（%）<input type="number" min="0.1" max="49" step="0.1" value={gridStepPercent} onChange={(event) => setGridStepPercent(event.target.value)} required /></label> : null}</div></div>
            <p className={canRunBacktest ? "data-ready" : "data-pending"}>{canRunBacktest ? `已找到 ${dataAvailability?.bar_count} 根日线，可运行回测。` : "请填写已导入股票的代码，并选择有数据覆盖的时间区间。"}</p>
            <button className="run-backtest" type="button" onClick={() => void handleRunBacktest()} disabled={!canRunBacktest || isRunningBacktest}>{isRunningBacktest ? "回测运行中…" : "运行回测"}</button>
            {backtestJob ? <div className="backtest-job"><span>任务状态：{backtestJob.status}</span>{["PENDING", "RUNNING"].includes(backtestJob.status) ? <button type="button" onClick={() => void handleCancelBacktest()}>取消任务</button> : null}</div> : null}
          </div>
          <div className="backtest-results">
            <header><div><p className="panel-kicker">RESULTS</p><h3>回测结果</h3></div>{backtest ? <span>{backtest.strategy}</span> : null}</header>
            {backtest ? <><div className="backtest-replay"><header><div><p className="panel-kicker">STRATEGY REPLAY</p><h3>策略复盘</h3></div><span>B 买入 · S 卖出</span></header>{backtest.daily_bars.length > 0 ? <CandlestickChart bars={backtest.daily_bars} tradeMarkers={backtest.trades} showNavigation={false} onOlder={() => undefined} onNewer={() => undefined} canShowOlder={false} canShowNewer={false} /> : <p className="replay-unavailable">该历史任务未保存行情快照，无法绘制可复现的 K 线图。</p>}</div><div className="metric-grid"><div><span>总收益</span><strong>{backtest.metrics.total_return}</strong></div><div><span>最大回撤</span><strong>{backtest.metrics.max_drawdown}</strong></div><div><span>年化夏普</span><strong>{backtest.metrics.annualized_sharpe}</strong></div><div><span>期末净值</span><strong>{backtest.equity_curve.at(-1)?.equity ?? "-"}</strong></div><div><span>成交次数</span><strong>{backtest.metrics.trade_count}</strong></div><div><span>总费用</span><strong>{backtest.metrics.total_fees}</strong></div></div><dl className="backtest-metadata"><dt>数据来源</dt><dd>{backtest.data_source}</dd><dt>复权口径</dt><dd>{backtest.adjustment_mode}</dd><dt>费用模型</dt><dd>{backtest.fee_model}</dd><dt>成交假设</dt><dd>{backtest.execution_assumption}</dd></dl><h3>成交明细</h3>{backtest.trades.length === 0 ? <p className="result-empty">本次回测没有产生模拟成交。</p> : <table><thead><tr><th>日期</th><th>方向</th><th>价格</th><th>数量</th><th>费用</th></tr></thead><tbody>{backtest.trades.map((trade) => <tr key={`${trade.trade_date}-${trade.side}`}><td>{trade.trade_date}</td><td>{trade.side}</td><td>{trade.price}</td><td>{trade.quantity}</td><td>{trade.fee}</td></tr>)}</tbody></table>}</> : <div className="result-empty"><h3>等待运行</h3><p>配置左侧参数并运行回测，结果将在这里展示。</p></div>}
          </div>
        </div>
        <section className="backtest-history" aria-labelledby="backtest-history">
          <header><div><p className="panel-kicker">HISTORY</p><h3 id="backtest-history">历史回测任务</h3></div><span>{backtestHistory.length}</span></header>
          {backtestHistory.length === 0 ? <p className="history-empty">尚无历史回测任务。完成一次回测后，任务会保存在这里。</p> : <table><thead><tr><th>创建时间</th><th>证券</th><th>区间</th><th>策略</th><th>状态</th><th>操作</th></tr></thead><tbody>{backtestHistory.map((job) => <tr key={job.id} className={backtestJob?.id === job.id ? "selected-history-job" : ""}><td>{job.created_at.replace("T", " ").slice(0, 16)}</td><td>{job.symbol.replace(/^[^:]+:/, "")}</td><td>{job.start} 至 {job.end}</td><td>{job.strategy_name}</td><td><span className={`job-status status-${job.status.toLowerCase()}`}>{job.status}</span></td><td><div className="history-actions"><button type="button" onClick={() => void handleViewBacktestHistory(job)}>查看</button><button type="button" onClick={() => restoreBacktestParameters(job)}>复制参数</button>{!["PENDING", "RUNNING"].includes(job.status) ? <button type="button" className="history-delete" onClick={() => void handleDeleteBacktestHistory(job)}>删除</button> : null}</div></td></tr>)}</tbody></table>}
        </section>
      </section> : null}
      {activeTab === "simulation" ? <section className="simulation-workspace" aria-labelledby="paper-trading">
        <header className="simulation-header"><div><p className="panel-kicker">PAPER TRADING</p><h2 id="paper-trading">模拟交易</h2><p>选择已导入行情的股票，以最近日线收盘价作为限价参考。</p></div><div className="simulation-header-actions"><span>本地模拟账户</span><button type="button" className="account-manager-button" onClick={() => setIsAccountManagerOpen(true)}>账户管理</button></div></header>
        {!simAccount ? (
          <div className="simulation-account-setup">
            <div><p className="panel-kicker">ACCOUNT SETUP</p><h3>创建模拟账户</h3><p>账户仅用于本地模拟撮合，不会连接真实证券账户或产生真实交易。</p></div>
            <label>
              账户名称
              <input maxLength={128} placeholder="例如：趋势策略测试" value={simAccountName} onChange={(event) => setSimAccountName(event.target.value)} />
            </label>
            <label>
              初始资金（元）
              <input type="number" min="1" placeholder="例如：100000" value={simInitialCash} onChange={(event) => setSimInitialCash(event.target.value)} />
            </label>
            <button type="button" onClick={() => void handleCreateSimAccount()}>创建模拟账户</button>
          </div>
        ) : (
          <>
            <div className="simulation-dashboard">
              <div className="simulation-ticket">
                <header><div><p className="panel-kicker">ORDER TICKET</p><h3>下单面板</h3></div><span>日线限价单</span></header>
                <label>
                  交易股票
                  <select value={simSymbol} onChange={(event) => setSimSymbol(event.target.value)}>
                    <option value="">请选择已导入股票</option>
                    {[...instruments].sort((left, right) => left.symbol.localeCompare(right.symbol)).map((instrument) => <option key={instrument.symbol} value={instrument.symbol}>{formatInstrumentLabel(instrument)}</option>)}
                  </select>
                </label>
                {instruments.length === 0 ? <p className="simulation-hint simulation-warning">暂无已导入股票。请先前往“日线行情”导入股票的历史日线。</p> : null}
                <div className="simulation-quote">
                  <span>最新日线收盘价</span>
                  {isLoadingSimQuote ? <strong>读取中…</strong> : simLatestBar ? <strong>{simLatestBar.close}</strong> : <strong>--</strong>}
                  <small>{simLatestBar ? `${simLatestBar.trade_date} 收盘` : "选择股票后自动读取"}</small>
                </div>
                <div className="simulation-order-fields">
                  <label>
                    限价（元）
                    <input type="number" min="0.01" step="0.01" placeholder="自动带入收盘价" value={simPrice} onChange={(event) => setSimPrice(event.target.value)} disabled={!isSimAccountActive || !simSymbol || isLoadingSimQuote} />
                  </label>
                  <label>
                    数量（股）
                    <input type="number" min="100" step="100" value={simQuantity} onChange={(event) => setSimQuantity(event.target.value)} disabled={!isSimAccountActive || !simSymbol || isLoadingSimQuote} />
                  </label>
                </div>
                <p className="simulation-hint">限价默认取最新日线“收”，可按需要修改；数量按 A 股整手（100 股）填写。</p>
                <div className="simulation-actions">
                  <button type="button" className="sim-buy" disabled={!isSimAccountActive || !simSymbol || !simLatestBar || isLoadingSimQuote || Number(simPrice) <= 0 || !isSimQuantityValid} onClick={() => void handleSimOrder("BUY")}>模拟买入</button>
                  <button type="button" className="sim-sell" disabled={!isSimAccountActive || !simSymbol || !simLatestBar || isLoadingSimQuote || Number(simPrice) <= 0 || !isSimQuantityValid} onClick={() => void handleSimOrder("SELL")}>模拟卖出</button>
                </div>
              </div>
              <div className="simulation-overview">
                <header><div><p className="panel-kicker">ACCOUNT OVERVIEW</p><h3>{simAccount.name}{!isSimAccountActive ? "（已归档）" : ""}</h3></div><button type="button" className="settlement-button" disabled={!isSimAccountActive} onClick={() => void handleSettlement()}>执行日终结算</button></header>
                <label className="sim-account-selector">模拟账户<select value={simAccount.id} onChange={(event) => void handleSelectSimAccount(event.target.value)}>{simAccounts.map((account) => <option key={account.id} value={account.id}>{`${account.name}${account.status === "ARCHIVED" ? "（已归档）" : ""} · ${account.created_at.replace("T", " ").slice(0, 16)}`}</option>)}</select></label>
                {!isSimAccountActive ? <p className="simulation-hint simulation-warning">该账户已归档，仅可查看历史记录；可在“账户管理”中恢复。</p> : null}
                <div className="simulation-metrics"><div><span>可用资金</span><strong>{simAccount.cash}</strong></div><div><span>冻结资金</span><strong>{simAccount.frozen_cash}</strong></div><div><span>当前持仓</span><strong>{simPositions.length}</strong></div><div><span>待处理订单</span><strong>{simOrders.filter((order) => ["ACCEPTED", "PARTIALLY_FILLED"].includes(order.status)).length}</strong></div></div>
                <div className="selected-sim-instrument"><span>当前标的</span><strong>{selectedSimInstrument ? formatInstrumentLabel(selectedSimInstrument) : "尚未选择股票"}</strong><small>{simLatestBar ? `最近交易日 ${simLatestBar.trade_date}` : "从左侧下单面板选择已导入股票"}</small></div>
                <p className="simulation-model-note">委托会经过资金、持仓与交易规则校验；成交与日终数据均为模拟结果。</p>
              </div>
            </div>
            <div className="simulation-records">
            <div className="simulation-data-panel"><h3>订单</h3>
            {simOrders.length === 0 ? <p>尚未提交订单。</p> : (
              <table>
                <thead><tr><th>方向</th><th>价格</th><th>数量</th><th>已成交</th><th>状态</th><th>原因</th><th>操作</th></tr></thead>
                <tbody>{simOrders.map((order) => (
                  <tr key={order.id}><td>{order.side}</td><td>{order.limit_price}</td><td>{order.quantity}</td><td>{order.filled_quantity}</td><td>{order.status}</td><td>{order.rejection_reason ?? "-"}</td><td>{["ACCEPTED", "PARTIALLY_FILLED"].includes(order.status) ? <button type="button" onClick={() => void handleCancelSimOrder(order.id)}>撤单</button> : "-"}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div><div className="simulation-data-panel"><h3>持仓</h3>
            {simPositions.length === 0 ? <p>当前无持仓。</p> : (
              <table>
                <thead><tr><th>证券</th><th>持仓</th><th>可卖（T+1）</th><th>冻结</th><th>成本</th></tr></thead>
                <tbody>{simPositions.map((position) => (
                  <tr key={position.symbol}><td>{position.symbol}</td><td>{position.quantity}</td><td>{position.available_quantity}</td><td>{position.frozen_quantity}</td><td>{position.average_cost}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div><div className="simulation-data-panel"><h3>成交记录</h3>
            {simFills.length === 0 ? <p>当前无成交记录。</p> : (
              <table>
                <thead><tr><th>委托</th><th>价格</th><th>数量</th><th>费用</th><th>成交时间</th></tr></thead>
                <tbody>{simFills.map((fill) => (
                  <tr key={fill.id}><td>{fill.order_id}</td><td>{fill.price}</td><td>{fill.quantity}</td><td>{fill.fee}</td><td>{fill.filled_at}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div><div className="simulation-data-panel"><h3>资金流水</h3>
            {cashLedger.length === 0 ? <p>当前无资金流水。</p> : (
              <table>
                <thead><tr><th>原因</th><th>金额</th><th>关联对象</th><th>发生时间</th></tr></thead>
                <tbody>{cashLedger.map((entry) => (
                  <tr key={entry.id}><td>{entry.reason}</td><td>{entry.amount}</td><td>{entry.reference_id}</td><td>{entry.created_at}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div><div className="simulation-data-panel"><h3>日终净值快照</h3>
            {accountSnapshots.length === 0 ? <p>执行日终结算后将生成净值快照。</p> : (
              <table>
                <thead><tr><th>日期</th><th>可用资金</th><th>冻结资金</th><th>持仓市值</th><th>净资产</th></tr></thead>
                <tbody>{accountSnapshots.map((snapshot) => (
                  <tr key={snapshot.as_of_date}><td>{snapshot.as_of_date}</td><td>{snapshot.cash}</td><td>{snapshot.frozen_cash}</td><td>{snapshot.market_value}</td><td>{snapshot.equity}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div><div className="simulation-data-panel"><h3>公司行动</h3>
            {corporateActionApplications.length === 0 ? <p>当前无已应用的公司行动。</p> : (
              <table>
                <thead><tr><th>类型</th><th>除息日</th><th>入账金额</th><th>应用时间</th></tr></thead>
                <tbody>{corporateActionApplications.map((application) => (
                  <tr key={application.corporate_action_id}><td>{application.action_type}</td><td>{application.ex_date}</td><td>{application.amount}</td><td>{application.applied_at}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div><div className="simulation-data-panel"><h3>风险事件</h3>
            {riskEvents.length === 0 ? <p>当前无风险事件。</p> : (
              <table>
                <thead><tr><th>规则</th><th>决策</th><th>详情</th></tr></thead>
                <tbody>{riskEvents.map((event) => (
                  <tr key={event.id}><td>{event.rule_code}</td><td>{event.decision}</td><td>{event.detail}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div><div className="simulation-data-panel"><h3>审计事件</h3>
            {auditEvents.length === 0 ? <p>当前无审计事件。</p> : (
              <table>
                <thead><tr><th>类别</th><th>动作</th><th>关联对象</th></tr></thead>
                <tbody>{auditEvents.map((event) => (
                  <tr key={event.id}><td>{event.category}</td><td>{event.action}</td><td>{event.reference_id}</td></tr>
                ))}</tbody>
              </table>
            )}
            </div>
            </div>
          </>
        )}
      </section> : null}
      {isAccountManagerOpen ? <div className="account-manager-backdrop" role="presentation" onMouseDown={() => setIsAccountManagerOpen(false)}><section className="account-manager-dialog" role="dialog" aria-modal="true" aria-labelledby="account-manager-title" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><p className="panel-kicker">ACCOUNT MANAGEMENT</p><h2 id="account-manager-title">模拟账户管理</h2><p>有订单、成交或持仓的账户保留审计记录，只能归档，不能删除。</p></div><button type="button" className="account-manager-close" aria-label="关闭账户管理" onClick={() => setIsAccountManagerOpen(false)}>×</button></header>
        <div className="account-manager-create"><div><h3>创建模拟账户</h3><p>新账户的交易与资金流水将独立记录。</p></div><label>账户名称<input maxLength={128} placeholder="例如：趋势策略测试" value={simAccountName} onChange={(event) => setSimAccountName(event.target.value)} /></label><label>初始资金（元）<input type="number" min="1" placeholder="例如：100000" value={simInitialCash} onChange={(event) => setSimInitialCash(event.target.value)} /></label><button type="button" onClick={() => void handleCreateSimAccount()}>创建账户</button></div>
        <div className="account-manager-list"><h3>账户列表</h3>{simAccounts.length === 0 ? <p>暂无模拟账户。</p> : simAccounts.map((account) => <article key={account.id} className={`managed-account ${simAccount?.id === account.id ? "current-managed-account" : ""}`}><div className="managed-account-info">{editingSimAccountId === account.id ? <div className="rename-account"><input aria-label="账户名称" maxLength={128} value={editingSimAccountName} onChange={(event) => setEditingSimAccountName(event.target.value)} /><button type="button" onClick={() => void handleRenameSimAccount(account.id)}>保存</button><button type="button" className="secondary-account-action" onClick={() => setEditingSimAccountId(undefined)}>取消</button></div> : <><strong>{account.name}</strong><span>{account.status === "ACTIVE" ? "活跃" : "已归档"} · 创建于 {account.created_at.replace("T", " ").slice(0, 16)}</span></>}</div><div className="managed-account-actions"><button type="button" className="secondary-account-action" onClick={() => void handleSelectSimAccount(account.id)}>查看</button>{editingSimAccountId !== account.id ? <button type="button" className="secondary-account-action" onClick={() => { setEditingSimAccountId(account.id); setEditingSimAccountName(account.name); }}>重命名</button> : null}{account.status === "ACTIVE" ? <button type="button" className="archive-account-action" onClick={() => void handleSetSimAccountStatus(account, "ARCHIVED")}>归档</button> : <button type="button" className="secondary-account-action" onClick={() => void handleSetSimAccountStatus(account, "ACTIVE")}>恢复</button>}<button type="button" className="delete-account-action" disabled={!account.can_delete} title={account.can_delete ? "删除空账户" : "已有交易记录的账户不能删除，请归档"} onClick={() => void handleDeleteSimAccount(account)}>{account.can_delete ? "删除" : "保留记录"}</button></div></article>)}</div>
      </section></div> : null}
      <p className="notice">模拟交易结果不代表真实成交或投资建议。</p>
    </main>
  );
}
