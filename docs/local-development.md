# 本地开发（SQLite + 同步任务）

本模式用于本机研究和 Tushare 联调，不需要 PostgreSQL、Redis、Docker 或 Celery Worker。数据保存在 `backend/a_share_quant_lab.db`；仅适合单进程开发，不应用于多人并发或生产部署。

## 配置

在项目根目录复制本地模板：

```powershell
Copy-Item .env.local.example .env
```

在 `.env` 中填写自己的 `TUSHARE_TOKEN`。该文件已被 Git 忽略，不能把 Token 写回 `.env.example`。

## 启动

```powershell
cd D:\src\northjhuang\kelly-bet-criterion
.\.venv\Scripts\Activate.ps1
python -m pip install -e .\backend[dev]

cd backend
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

无需启动 Celery Worker。`POST /api/v1/data/imports` 会在当前 API 进程中完成抓取和落库；较长日期范围会阻塞该 HTTP 请求，因此建议先以单个证券、较短日期范围验证。

前端在另一个 PowerShell 窗口启动：

```powershell
cd D:\src\northjhuang\kelly-bet-criterion
corepack enable
corepack pnpm install
corepack pnpm --filter a-share-quant-lab-frontend run dev
```

## 验证顺序

1. 打开 `http://localhost:8000/docs`，确认健康检查成功。
2. 调用 `POST /api/v1/data/imports` 导入 Tushare 日线数据。
3. 使用 `GET /api/v1/data/imports/{job_id}` 确认状态为 `COMPLETED`。
4. 调用 `POST /api/v1/backtests`。`BACKTEST_MARKET_DATA=database` 会使用刚导入的有效行情。

切回完整部署时，将 `DATABASE_URL` 改为 PostgreSQL 地址、`TASK_EXECUTION_MODE=celery`，并启动 Redis 和 Worker。
