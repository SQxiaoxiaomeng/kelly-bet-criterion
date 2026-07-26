from datetime import UTC, date, datetime
from decimal import Decimal

from app.providers.base import RawCashDividend, RawDailyBar, RawInstrument, RawTradingDay


class TushareMarketDataProvider:
    """Tushare Pro daily-bar adapter. The token is injected from backend configuration."""

    name = "tushare"

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("TUSHARE_TOKEN_NOT_CONFIGURED")
        self._token = token

    def fetch_instruments(self, symbols: list[str]) -> list[RawInstrument]:
        import tushare as ts  # type: ignore[import-untyped]

        pro = ts.pro_api(self._token)
        instruments: list[RawInstrument] = []
        for symbol in symbols:
            response = pro.stock_basic(
                ts_code=_to_tushare_symbol(symbol), fields="ts_code,name,market"
            )
            for row in response.to_dict("records"):
                instruments.append(
                    RawInstrument(
                        symbol=_from_tushare_symbol(str(row["ts_code"])),
                        name=str(row["name"]),
                        board=_to_board(str(row.get("market") or "")),
                    )
                )
        return instruments

    def fetch_daily_bars(self, symbols: list[str], start: date, end: date) -> list[RawDailyBar]:
        import tushare as ts

        pro = ts.pro_api(self._token)
        bars: list[RawDailyBar] = []
        for symbol in symbols:
            response = pro.daily(
                ts_code=_to_tushare_symbol(symbol),
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
            for row in response.to_dict("records"):
                bars.append(
                    RawDailyBar(
                        symbol=_from_tushare_symbol(str(row["ts_code"])),
                        trade_date=datetime.strptime(str(row["trade_date"]), "%Y%m%d").date(),
                        open=Decimal(str(row["open"])),
                        high=Decimal(str(row["high"])),
                        low=Decimal(str(row["low"])),
                        close=Decimal(str(row["close"])),
                        volume=Decimal(str(row["vol"])) * Decimal("100"),
                        amount=Decimal(str(row["amount"])) * Decimal("1000"),
                        published_at=datetime.now(UTC),
                    )
                )
        return sorted(bars, key=lambda item: (item.symbol, item.trade_date))

    def fetch_trading_calendar(
        self, exchange: str, start: date, end: date
    ) -> list[RawTradingDay]:
        if exchange not in {"SSE", "SZSE"}:
            raise ValueError("UNSUPPORTED_EXCHANGE")
        import tushare as ts

        response = ts.pro_api(self._token).trade_cal(
            exchange=exchange,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        return [
            RawTradingDay(
                exchange=exchange,
                trade_date=datetime.strptime(str(row["cal_date"]), "%Y%m%d").date(),
                is_open=str(row["is_open"]) == "1",
            )
            for row in response.to_dict("records")
        ]

    def fetch_cash_dividends(
        self, symbols: list[str], start: date, end: date
    ) -> list[RawCashDividend]:
        import tushare as ts

        pro = ts.pro_api(self._token)
        dividends: list[RawCashDividend] = []
        for symbol in symbols:
            response = pro.dividend(ts_code=_to_tushare_symbol(symbol))
            for row in response.to_dict("records"):
                ex_date = row.get("ex_date")
                cash_div = row.get("cash_div")
                if not ex_date or cash_div is None:
                    continue
                action_date = datetime.strptime(str(ex_date), "%Y%m%d").date()
                if not start <= action_date <= end:
                    continue
                dividends.append(
                    RawCashDividend(
                        symbol=symbol,
                        ex_date=action_date,
                        cash_per_share=Decimal(str(cash_div)),
                        published_at=(
                            datetime.strptime(str(row["ann_date"]), "%Y%m%d").replace(tzinfo=UTC)
                            if row.get("ann_date")
                            else None
                        ),
                    )
                )
        return sorted(dividends, key=lambda item: (item.symbol, item.ex_date))


def _to_tushare_symbol(symbol: str) -> str:
    exchange, code = symbol.split(":", maxsplit=1)
    suffix = {"SSE": "SH", "SZSE": "SZ"}.get(exchange)
    if suffix is None:
        raise ValueError("UNSUPPORTED_EXCHANGE")
    return f"{code}.{suffix}"


def _from_tushare_symbol(symbol: str) -> str:
    code, suffix = symbol.split(".", maxsplit=1)
    exchange = {"SH": "SSE", "SZ": "SZSE"}.get(suffix)
    if exchange is None:
        raise ValueError("UNSUPPORTED_TUSHARE_SYMBOL")
    return f"{exchange}:{code}"


def _to_board(market: str) -> str:
    return {
        "主板": "MAIN",
        "创业板": "GEM",
        "科创板": "STAR",
        "北交所": "BSE",
    }.get(market, "UNKNOWN")
