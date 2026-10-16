import app.tasks.prices  # noqa: F401  регистрирует shared_task
from app.config import Settings
from app.tasks.celery_app import COLLECT_INDEX_PRICES_TASK, create_celery_app


def test_celery_app_uses_redis_broker_from_settings(settings: Settings) -> None:
    celery_app = create_celery_app(settings)

    assert celery_app.conf.broker_url == settings.redis_url


def test_beat_runs_price_collection_every_minute(settings: Settings) -> None:
    celery_app = create_celery_app(settings)

    entry = celery_app.conf.beat_schedule["collect-index-prices"]
    assert entry["task"] == COLLECT_INDEX_PRICES_TASK
    assert entry["schedule"] == 60
    assert entry["options"] == {"expires": 60}


def test_collect_task_is_registered(settings: Settings) -> None:
    celery_app = create_celery_app(settings)

    assert COLLECT_INDEX_PRICES_TASK in celery_app.tasks
