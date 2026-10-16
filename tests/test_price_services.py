import asyncio
import logging
from collections.abc import Sequence
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.clients.deribit import DeribitClientError
from app.db.models import Price
from app.repositories.price import PriceRepository
from app.services.price import PriceCollectorService, PriceQueryService
from app.tickers import Ticker

NOW = 1792138758.987


class FakeDeribitClient:
    """Возвращает заданную цену или бросает заданное исключение."""

    def __init__(self, responses: dict[Ticker, Decimal | Exception]) -> None:
        self._responses = responses

    async def get_index_price(self, ticker: Ticker) -> Decimal:
        response = self._responses[ticker]
        if isinstance(response, Exception):
            raise response
        return response


class ConcurrencyCheckingClient:
    """Отвечает только после того, как стартовали все запросы.

    Если запросы идут последовательно, первый не дождётся ответа.
    """

    def __init__(self, expected_requests: int) -> None:
        self._expected_requests = expected_requests
        self._started = 0
        self._all_started = asyncio.Event()

    async def get_index_price(self, ticker: Ticker) -> Decimal:
        self._started += 1
        if self._started == self._expected_requests:
            self._all_started.set()
        await self._all_started.wait()
        return Decimal("1")


class FakePriceRepository:
    """Сохраняет пачки цен в список вместо БД."""

    def __init__(self) -> None:
        self.saved_batches: list[Sequence[Price]] = []

    async def add_many(self, prices: Sequence[Price]) -> None:
        self.saved_batches.append(prices)


@pytest.fixture
def repository() -> FakePriceRepository:
    return FakePriceRepository()


def make_collector(
    client: object, repository: FakePriceRepository
) -> PriceCollectorService:
    return PriceCollectorService(client, repository, clock=lambda: NOW)


async def test_collect_saves_all_prices_in_one_batch_with_shared_timestamp(
    repository: FakePriceRepository,
) -> None:
    client = FakeDeribitClient(
        {Ticker.BTC_USD: Decimal("82153.93"), Ticker.ETH_USD: Decimal("2452.6")}
    )

    saved = await make_collector(client, repository).collect()

    assert saved == 2
    assert len(repository.saved_batches) == 1
    batch = repository.saved_batches[0]
    assert {(p.ticker, p.price) for p in batch} == {
        ("btc_usd", Decimal("82153.93")),
        ("eth_usd", Decimal("2452.6")),
    }
    # целые секунды, одинаковые для всей пачки
    assert {p.timestamp for p in batch} == {1792138758}


async def test_collect_saves_other_tickers_when_one_fails(
    repository: FakePriceRepository, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeDeribitClient(
        {
            Ticker.BTC_USD: Decimal("82153.93"),
            Ticker.ETH_USD: DeribitClientError("HTTP 503"),
        }
    )

    with caplog.at_level(logging.ERROR):
        saved = await make_collector(client, repository).collect()

    assert saved == 1
    [batch] = repository.saved_batches
    assert [(p.ticker, p.price) for p in batch] == [("btc_usd", Decimal("82153.93"))]
    assert "eth_usd" in caplog.text
    assert "HTTP 503" in caplog.text


async def test_collect_saves_nothing_when_all_tickers_fail(
    repository: FakePriceRepository, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeDeribitClient(
        {ticker: DeribitClientError("timeout") for ticker in Ticker}
    )

    with caplog.at_level(logging.WARNING):
        saved = await make_collector(client, repository).collect()

    assert saved == 0
    assert repository.saved_batches == []
    assert "nothing to save" in caplog.text


async def test_collect_requests_tickers_concurrently(
    repository: FakePriceRepository,
) -> None:
    client = ConcurrencyCheckingClient(expected_requests=len(Ticker))

    saved = await asyncio.wait_for(make_collector(client, repository).collect(), 1)

    assert saved == len(Ticker)


async def test_collect_does_not_swallow_unexpected_errors(
    repository: FakePriceRepository,
) -> None:
    client = FakeDeribitClient(
        {Ticker.BTC_USD: Decimal("1"), Ticker.ETH_USD: RuntimeError("bug")}
    )

    with pytest.raises(RuntimeError, match="bug"):
        await make_collector(client, repository).collect()

    assert repository.saved_batches == []


async def test_query_service_delegates_to_repository() -> None:
    repository = AsyncMock(spec=PriceRepository)
    service = PriceQueryService(repository)

    await service.get_all(Ticker.BTC_USD, limit=10, offset=5)
    await service.get_latest(Ticker.ETH_USD)
    await service.get_by_period(Ticker.BTC_USD, start=100, end=200, limit=10, offset=0)

    repository.get_all.assert_awaited_once_with(Ticker.BTC_USD, limit=10, offset=5)
    repository.get_latest.assert_awaited_once_with(Ticker.ETH_USD)
    repository.get_by_period.assert_awaited_once_with(
        Ticker.BTC_USD, start=100, end=200, limit=10, offset=0
    )
