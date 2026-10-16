import asyncio
import logging

import aiohttp
from celery import shared_task

from app.clients.deribit import DeribitClient
from app.config import Settings, get_settings
from app.db.session import build_engine, build_session_factory
from app.repositories.price import PriceRepository
from app.services.price import PriceCollectorService
from app.tasks.celery_app import COLLECT_INDEX_PRICES_TASK

logger = logging.getLogger(__name__)


@shared_task(name=COLLECT_INDEX_PRICES_TASK)
def collect_index_prices() -> int:
    """Получает индексные цены с Deribit и сохраняет их в БД."""
    return asyncio.run(_collect_index_prices(get_settings()))


async def _collect_index_prices(settings: Settings) -> int:
    # asyncio.run создаёт новый event loop при каждом запуске, а соединения
    # asyncpg и aiohttp к нему привязаны, поэтому engine и сессия свои на запуск
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    timeout = aiohttp.ClientTimeout(total=settings.deribit_timeout_seconds)
    try:
        async with (
            aiohttp.ClientSession() as http_session,
            session_factory() as db_session,
        ):
            service = PriceCollectorService(
                client=DeribitClient(
                    http_session, settings.deribit_base_url, timeout=timeout
                ),
                repository=PriceRepository(db_session),
            )
            return await service.collect()
    finally:
        await engine.dispose()
        logger.debug("Database engine disposed")
