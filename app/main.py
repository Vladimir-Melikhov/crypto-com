from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health, prices
from app.config import Settings, get_settings
from app.db.session import build_engine, build_session_factory
from app.logging_config import configure_logging

API_DESCRIPTION = (
    "API для получения индексных цен btc_usd и eth_usd, "
    "которые раз в минуту сохраняются с биржи Deribit."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Создаёт приложение FastAPI."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings.database_url)
        app.state.session_factory = build_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="Deribit Index Prices API",
        description=API_DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(prices.router)
    app.include_router(health.router)
    return app
