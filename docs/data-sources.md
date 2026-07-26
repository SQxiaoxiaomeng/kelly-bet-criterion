# Data Sources

## Tushare Pro Configuration

Tushare Pro is implemented as an optional adapter for A-share daily OHLCV, trading calendars, and cash-dividend corporate actions. It is intended for end-of-day research and backtesting, not real-time trading.

1. Register with Tushare and obtain a personal token. Do not commit it to the repository.
2. Copy `.env.example` to `.env`, then set `MARKET_DATA_PROVIDER=tushare` and `TUSHARE_TOKEN=your-token`.
3. Start the API, PostgreSQL, Redis, and Celery Worker. Create an asynchronous import with `POST /api/v1/data/imports`, then query it through `GET /api/v1/data/imports/{job_id}`.

The adapter normalizes Tushare codes such as `600000.SH` to `SSE:600000`; its `vol` unit is converted from lots to shares and `amount` from thousands of yuan to yuan. Cash-dividend imports require a usable ex-date and positive `cash_div`; stock dividends, splits and rights issues are not yet supported. Tushare account permissions, historical range, request rate and redistribution terms can change; follow its current official documentation and the permissions granted to the account. If a token is absent, the upstream is limited, or a request fails, the import job is marked failed while existing data remains unchanged. Use the deterministic Fixture Provider for local development without a token.

To run a backtest against imported bars instead of the built-in fixture, set `BACKTEST_MARKET_DATA=database`. The backtest then filters by the configured `MARKET_DATA_PROVIDER` and records a hash derived from the immutable bar IDs as its input snapshot identifier. This is a daily-bar research assumption, not evidence of executable intraday prices.

本文件记录接入数据源的许可证、字段范围、更新频率、延迟和降级策略。没有完成登记的数据源不得作为默认生产链路。

| Provider | 状态 | 数据范围 | 许可 / 使用边界 | 降级策略 |
|---|---|---|---|---|
| Fixture Provider | 已启用（测试） | 固定的日线样本 | 仅用于自动化测试；不包含真实行情。 | 无需降级。 |
| 免费 A 股 Provider | 待评审 | 待确认 | 接入前确认公开条款、频率限制与再分发限制。 | 任务失败可见；不将旧数据伪装为新数据。 |
