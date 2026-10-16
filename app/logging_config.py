import logging

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str) -> None:
    """Настраивает логирование для API (у Celery своя настройка логов)."""
    logging.basicConfig(level=level, format=LOG_FORMAT)
