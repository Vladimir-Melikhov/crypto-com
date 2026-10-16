from celery import Celery

from app.config import Settings

COLLECT_INDEX_PRICES_TASK = "prices.collect_index_prices"


def create_celery_app(settings: Settings) -> Celery:
    """Создаёт приложение Celery с брокером Redis и расписанием для beat."""
    interval = settings.price_collection_interval_seconds
    celery_app = Celery(
        "deribit_prices",
        broker=settings.redis_url,
        include=["app.tasks.prices"],
    )
    celery_app.conf.update(
        timezone="UTC",
        enable_utc=True,
        # Результат задачи не нужен, цены сохраняются в БД
        task_ignore_result=True,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "collect-index-prices": {
                "task": COLLECT_INDEX_PRICES_TASK,
                "schedule": interval,
                # Если воркер был недоступен, старые задачи не выполняются
                "options": {"expires": interval},
            },
        },
    )
    return celery_app
