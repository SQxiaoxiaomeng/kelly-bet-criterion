# a-share-quant-lab

前后端分离的 A 股量化研究、日频回测与模拟交易平台。系统只用于研究和模拟，不连接券商、不操作真实资金。

## 当前能力

- 免费数据 Provider 抽象，内置 Fixture 与 Tushare 日线适配器；行情记录来源、时间和质量状态。
- SQLite 本地运行模式，不依赖 PostgreSQL、Redis 或 Docker。
- Tushare/Fixture 交易日历同步；Celery 日终结算在日历缺失或非交易日安全跳过。
- 单证券日频回测：双均线、买入并持有、数据快照、策略版本、费用、换手率、夏普与最大回撤。
- 回测任务创建、查询、前端轮询与取消；Celery 部署模式可选。
- 模拟账户、幂等限价委托、T+1、最小交易单位、涨跌停、停牌、费用、资金/证券冻结、撤单、日终结算与净值快照。
- 日线成交量近似下的部分成交，成交记录、资金流水、持仓、风控事件和审计事件查询。

## 本地启动（SQLite + Tushare）

先在项目根目录创建 `.env`。不要把真实 Token 提交到版本库。

```dotenv
DATABASE_URL=sqlite:///./a_share_quant_lab.db
BACKTEST_REPOSITORY=sql
BACKTEST_MARKET_DATA=database
TASK_EXECUTION_MODE=local
MARKET_DATA_PROVIDER=tushare
TUSHARE_TOKEN=你的_token
MAX_ORDER_NOTIONAL=1000000
```

PowerShell 中执行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开一个 PowerShell 窗口启动前端：

```powershell
cd D:\src\northjhuang\kelly-bet-criterion
corepack pnpm --filter a-share-quant-lab-frontend run dev
```

如果本机未安装 pnpm，可先执行 `corepack enable`，或安装 Node.js LTS 后重开终端。访问：

- 前端：`http://localhost:5173`
- 健康检查：`http://localhost:8000/api/v1/health`
- OpenAPI：`http://localhost:8000/docs`

前端使用三个独立页面：

- **真实日线行情**：输入 `SSE:600000`、`SZSE:000001` 这类代码后，同步该股票全量历史日线；后续再次同步只从本地最新日线的下一天开始更新。点击已导入股票可查看日 K。
- **日频回测**：选择股票、策略和具体开始/结束日期后运行回测。
- **模拟交易**：创建模拟账户后下单、撤单、查看成交、资金流水和日终快照。

## 验证

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\ruff.exe check app tests
..\.venv\Scripts\mypy.exe app tests

cd ..
corepack pnpm --filter a-share-quant-lab-frontend run lint
corepack pnpm --filter a-share-quant-lab-frontend run build
```

## 已知边界

- 模拟撮合基于最新有效日线的限价近似，不代表盘中排队或真实成交。
- 部分成交容量默认是对应日线成交量的 10%，并按 100 股向下取整。
- 除权除息/分红等公司行动、组合级风控、分钟线、实时 WebSocket、多用户权限和备份恢复尚未实现。
- 免费数据可能有延迟、缺失或接口限额；使用前请自行确认数据源许可。

## 文档

- [需求分析](docs/a-share-quant-trading-requirements-v0.1.md)
- [系统设计](docs/system-design-v0.1.md)
- [实施计划](docs/implementation-plan-v0.1.md)
- [本地开发](docs/local-development.md)
- [模拟交易运行手册](docs/simulation-runbook.md)
- [数据源登记](docs/data-sources.md)
- [开发规则](AGENTS.md)
