from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Price
from app.tickers import Ticker


class PriceRepository:
    """Запросы к таблице prices."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(self, prices: Sequence[Price]) -> None:
        """Сохраняет цены одной транзакцией."""
        self._session.add_all(prices)
        await self._session.commit()

    async def get_all(
        self,
        ticker: Ticker,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> Sequence[Price]:
        """Возвращает цены тикера, отсортированные по времени."""
        query = self._ordered_by_time(ticker)
        return await self._fetch_page(query, limit=limit, offset=offset)

    async def get_latest(self, ticker: Ticker) -> Price | None:
        """Возвращает последнюю цену тикера или None, если цен нет."""
        query = (
            select(Price)
            .where(Price.ticker == ticker.value)
            .order_by(Price.timestamp.desc(), Price.id.desc())
            .limit(1)
        )
        return await self._session.scalar(query)

    async def get_by_period(
        self,
        ticker: Ticker,
        *,
        start: int | None = None,
        end: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> Sequence[Price]:
        """Возвращает цены тикера с timestamp от start до end включительно.

        Если граница не передана, она не учитывается.
        """
        query = self._ordered_by_time(ticker)
        if start is not None:
            query = query.where(Price.timestamp >= start)
        if end is not None:
            query = query.where(Price.timestamp <= end)
        return await self._fetch_page(query, limit=limit, offset=offset)

    @staticmethod
    def _ordered_by_time(ticker: Ticker) -> Select[tuple[Price]]:
        # Сортировка по id дополнительно, чтобы порядок при одинаковом
        # timestamp был стабильным для пагинации
        return (
            select(Price)
            .where(Price.ticker == ticker.value)
            .order_by(Price.timestamp, Price.id)
        )

    async def _fetch_page(
        self,
        query: Select[tuple[Price]],
        *,
        limit: int | None,
        offset: int,
    ) -> Sequence[Price]:
        query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        result = await self._session.scalars(query)
        return result.all()
