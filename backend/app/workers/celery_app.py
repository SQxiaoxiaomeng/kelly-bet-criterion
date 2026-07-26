from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()
celery_app = Celery(
    "a_share_quant_lab",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.backtest_tasks",
        "app.workers.data_import_tasks",
        "app.workers.settlement_tasks",
    ],
)
celery_app.conf.task_track_started = True
celery_app.conf.timezone = "Asia/Shanghai"
celery_app.conf.beat_schedule = {
    "settle-simulated-accounts": {
        "task": "simulated_trading.settle_all",
        "schedule": crontab(hour=15, minute=10),
    }
}
