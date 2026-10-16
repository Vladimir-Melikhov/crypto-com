import asyncio
import logging
import time
from collections.abc import Callable, Iterable, Sequence
from decimal import Decimal

from app.clients.deribit import DeribitClient, DeribitClientError
from app.db.models import Price
from app.repositories.price import PriceRepository
from app.tickers import Ticker

logger = logging.getLogger(__name__)


class PriceCollectorService:
    """Получает индексные цены с биржи и сохраняет их в БД."""

    def __init__(
        self,
        client: DeribitClient,
        repository: PriceRepository,
        tickers: Iterable[Ticker] = tuple(Ticker),
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client = client
        self._repository = repository
        self._tickers = tuple(tickers)
        self._clock = clock

    async def collect(self) -> int:
        """Запрашивает цены всех тикеров и сохраняет их с общим timestamp.

        Если по одному тикеру цену получить не удалось, остальные всё равно
        сохраняются. Возвращает количество сохранённых цен.
        """
        timestamp = int(self._clock())
        prices = await asyncio.gather(
            *(self._fetch_price(ticker) for ticker in self._tickers)
        )
        records = [
            Price(ticker=ticker.value, price=price, timestamp=timestamp)
            for ticker, price in zip(self._tickers, prices, strict=True)
            if price is not None
        ]
        if not records:
            logger.warning("No index prices fetched at %d, nothing to save", timestamp)
            return 0

        await self._repository.add_many(records)
        logger.info(
            "Saved %d index price(s) at %d: %s",
            len(records),
            timestamp,
            ", ".join(f"{record.ticker}={record.price}" for record in records),
        )
        return len(records)

    async def _fetch_price(self, ticker: Ticker) -> Decimal | None:
        try:
            return await self._client.get_index_price(ticker)
        except DeribitClientError as exc:
            logger.error("Failed to fetch index price for %s: %s", ticker.value, exc)
            return None


class PriceQueryService:
    """Чтение сохранённых цен для API."""

    def __init__(self, repository: PriceRepository) -> None:
        self._repository = repository

    async def get_all(
        self, ticker: Ticker, *, limit: int, offset: int
    ) -> Sequence[Price]:
        """Возвращает все цены тикера постранично."""
        return await self._repository.get_all(ticker, limit=limit, offset=offset)

    async def get_latest(self, ticker: Ticker) -> Price | None:
        """Возвращает последнюю цену тикера."""
        return await self._repository.get_latest(ticker)

    async def get_by_period(
        self,
        ticker: Ticker,
        *,
        start: int | None,
        end: int | None,
        limit: int,
        offset: int,
    ) -> Sequence[Price]:
        """Возвращает цены тикера за период (UNIX timestamp в секундах)."""
        return await self._repository.get_by_period(
            ticker, start=start, end=end, limit=limit, offset=offset
        )
