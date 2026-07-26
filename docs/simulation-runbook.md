# 模拟交易运行手册

## 运行模式

本项目只支持模拟交易，不会连接券商或真实资金账户。推荐本地使用 SQLite 和同步任务模式；生产式开发环境可使用 PostgreSQL、Redis、Celery Worker。

## 本地启动

1. 在项目根目录创建 `.env`，参考 `.env.local.example`，填写自己的 `TUSHARE_TOKEN`。
2. 执行 `cd backend; alembic upgrade head`。
3. 执行 `python -m uvicorn app.main:app --reload --port 8000`。
4. 在根目录执行 `corepack pnpm --filter a-share-quant-lab-frontend run dev`。

如需启用 Celery Beat 的自动日终结算，先同步交易日历；日历缺失时任务会安全跳过，而不会猜测周末或法定节假日：

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/data/calendars/sync `
  -ContentType 'application/json' `
  -Body '{"exchange":"SSE","start":"2026-01-01","end":"2026-12-31"}'
```

## 模拟交易流程

1. 导入日线行情；模拟盘依据最新一根有效日线进行限价成交判断。
2. 创建模拟账户；初始入金会写入不可变资金流水。
3. 提交带 `Idempotency-Key` 的限价买卖单。买入冻结资金，卖出冻结满足 T+1 的持仓批次。
4. 市场价格满足限价条件时立即生成模拟成交；单次成交量按日线成交量的 10% 且向下取整至 100 股估算，可能形成 `PARTIALLY_FILLED`。未满足时订单保持 `ACCEPTED`，可撤单或执行日终结算。
5. 日终结算会使未完成订单（含部分成交的剩余数量）变为 `EXPIRED` 并释放冻结资源；已成交部分保留在成交记录、持仓批次和资金流水中，同时生成当日现金、冻结资金、市值和净资产快照。

在 Redis + Celery 部署模式下，Compose 中的 `scheduler` 服务会在 `Asia/Shanghai` 每日 15:10 触发账户结算任务；任务读取本地 SSE 交易日历，非交易日或日历尚未同步时会安全跳过。

## 可观测性

- `GET /api/v1/operations/status`：数据库、任务模式、行情与回测数据模式。
- `GET /api/v1/sim/accounts/{account_id}/orders`：订单状态。
- `GET /api/v1/sim/accounts/{account_id}/positions`：持仓、可卖与冻结数量。
- `GET /api/v1/sim/accounts/{account_id}/fills`：不可变成交记录。
- `GET /api/v1/sim/accounts/{account_id}/cash-ledger`：资金流水，用于与账户现金核对。
- `GET /api/v1/sim/accounts/{account_id}/snapshots`：日终净值快照。
- `GET /api/v1/sim/accounts/{account_id}/risk-events`：风控拒绝事件。

## 风险与限制

- 当前撮合是最新有效日线的限价近似，不代表盘中真实排队或实际成交。
- 当前基础风控包含交易规则、T+1、可用资金和单笔名义金额上限；`MAX_ORDER_NOTIONAL` 可在 `.env` 配置。
- 除权除息、公司行动、停复牌日历、组合级风险和分钟线仍需要在扩大使用范围前继续完善。
