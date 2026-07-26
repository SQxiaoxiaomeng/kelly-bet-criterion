from datetime import datetime
from zoneinfo import ZoneInfo

from app.application.paper_trading import PaperTradingService
from app.application.trading_calendar import TradingCalendarService
from app.core.config import get_settings
from app.infrastructure.database import create_session_factory
from app.workers.celery_app import celery_app


@celery_app.task(name="simulated_trading.settle_all")  # type: ignore[untyped-decorator]
def settle_all_accounts() -> dict[str, int | str]:
    settings = get_settings()
    trade_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    calendar = TradingCalendarService(create_session_factory())
    is_open = calendar.is_open("SSE", trade_date)
    if is_open is not True:
        return {
            "expired_order_count": 0,
            "status": "SKIPPED_CALENDAR_UNAVAILABLE" if is_open is None else "SKIPPED_CLOSED",
        }
    service = PaperTradingService(
        create_session_factory(),
        settings.market_data_provider,
        settings.max_order_notional,
        settings.max_single_position_ratio,
        settings.max_total_position_ratio,
    )
    expired_order_count = sum(
        service.settle_end_of_day(account_id).expired_order_count
        for account_id in service.list_active_account_ids()
    )
    return {"expired_order_count": expired_order_count, "status": "COMPLETED"}
