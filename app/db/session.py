from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    """Создаёт async-engine с пулом соединений к PostgreSQL."""
    return create_async_engine(database_url, pool_pre_ping=True)


def build_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Создаёт фабрику сессий, привязанную к engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
