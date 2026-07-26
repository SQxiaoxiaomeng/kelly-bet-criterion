# a-share-quant-lab

前后端分离的 A 股量化研究、日频回测与模拟交易平台。仅用于研究和模拟，不连接券商或操作真实资金。

## 当前功能

- **日线行情**：输入 6 位股票代码即可导入历史日线；代码自动识别沪深交易所。已导入股票支持搜索、查看日 K、删除和行级增量更新。
- **Tushare 数据适配**：日线、证券主数据和交易日历通过 Provider 层接入；日线写入 SQLite 时保留来源、观察时间和质量状态。
- **日频回测**：支持双均线、买入并持有、长仓网格策略；展示收益、回撤、夏普、费用、成交明细和带 B/S 标记的 K 线复盘图。
- **模拟交易**：本地模拟账户、限价委托、T+1、整手交易、费用、部分成交、撤单、日终结算、持仓、资金流水、风险与审计记录。
- **账户管理**：创建、重命名、切换、归档和恢复模拟账户；仅空账户可删除，含交易历史的账户保留审计记录并只能归档。
- **本地运行**：SQLite + 本地同步任务模式，不需要 PostgreSQL、Redis 或 Docker。

## 本地启动（SQLite + Tushare）

### 1. 创建本地配置

在项目根目录创建 `.env`。真实 Token 不应提交到 Git。

```dotenv
DATABASE_URL=sqlite:///./a_share_quant_lab.db
BACKTEST_REPOSITORY=sql
BACKTEST_MARKET_DATA=database
TASK_EXECUTION_MODE=local
MARKET_DATA_PROVIDER=tushare
TUSHARE_TOKEN=你的_Tushare_Token
MAX_ORDER_NOTIONAL=1000000
```

### 2. 启动后端

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. 启动前端

另开一个 PowerShell 窗口，在项目根目录执行。若终端当前已经位于项目根目录，可省略第一行；`corepack enable` 也只需在首次配置 Node.js 环境时执行一次。

```powershell
Set-Location <项目根目录>
# 例如：Set-Location D:\src\kelly-bet-criterion

# 首次启动时安装前端依赖
corepack enable
corepack pnpm install

# 每次启动前端时执行
corepack pnpm --filter a-share-quant-lab-frontend run dev
```

访问地址：

- 前端：http://localhost:5173
- 健康检查：http://localhost:8000/api/v1/health
- OpenAPI：http://localhost:8000/docs

## 使用流程

1. 在“日线行情”输入股票代码，例如 `600000` 或 `688036`，点击“添加”。
2. 点击股票池中的股票查看日 K；后续点击该行“更新”只抓取本地最新日线之后的新数据。
3. 在“日频回测”选择已导入股票、时间范围和策略后运行。网格策略的“网格间距”表示相邻买卖触发价格的百分比。
4. 在“模拟交易”创建并命名模拟账户，选择已导入股票；系统用最近日线收盘价作为限价参考。

> 日频回测的默认成交假设是：收盘生成信号，下一交易日开盘模拟成交。模拟交易和回测结果均不代表真实成交或投资建议。

## 数据同步说明

- 首次导入从 1990-01-01（或证券上市后可获得的数据）开始抓取；再次点击“更新”会从本地最新日线的下一天增量同步并去重。
- 当前本地模式**不会自动每日拉取日线**；需要手动点击每只股票的“更新”。
- Tushare 的 `stock_basic`、分钟数据等接口可能受积分与频率限制。主数据同步失败时，日线导入可继续执行，名称可能暂时显示为代码。
- 当前实现为日线研究系统；分钟线、实时行情和逐笔数据尚未接入。

## 验证

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check app tests
..\.venv\Scripts\python.exe -m mypy app

cd ..
corepack pnpm --filter a-share-quant-lab-frontend run lint
corepack pnpm --filter a-share-quant-lab-frontend run build
```

## 已知边界

- 模拟撮合基于日线价格和成交量近似，不能代表盘中排队或真实成交。
- 同日买入的股票受 A 股 T+1 限制，下一交易日才可卖出。
- 除权除息、分红等公司行为仅实现部分能力；组合级风控、多用户、分钟线和实时行情仍待完善。
- 免费数据可能有延迟、缺失、限流或许可限制，使用前请确认数据源条款。

## 相关文档

- [需求分析](docs/a-share-quant-trading-requirements-v0.1.md)
- [系统设计](docs/system-design-v0.1.md)
- [实施计划](docs/implementation-plan-v0.1.md)
- [本地开发](docs/local-development.md)
- [模拟交易运行手册](docs/simulation-runbook.md)
- [数据源登记](docs/data-sources.md)
- [开发规则](AGENTS.md)
