import asyncio
import socket
from collections.abc import AsyncIterator
from decimal import Decimal

import aiohttp
import pytest
from aiohttp import test_utils, web

from app.clients.deribit import DeribitClient, DeribitClientError
from app.tickers import Ticker

API_PREFIX = "/api/v2"


class FakeDeribit:
    """Локальный HTTP-сервер вместо Deribit с настраиваемым ответом."""

    def __init__(self) -> None:
        self.base_url = ""
        self.status = 200
        self.body = '{"jsonrpc": "2.0", "result": {"index_price": 1}}'
        self.delay_seconds = 0.0
        self.received_queries: list[dict[str, str]] = []

    async def handle(self, request: web.Request) -> web.Response:
        self.received_queries.append(dict(request.query))
        await asyncio.sleep(self.delay_seconds)
        return web.Response(
            status=self.status, text=self.body, content_type="application/json"
        )


@pytest.fixture
async def fake_deribit() -> AsyncIterator[FakeDeribit]:
    fake = FakeDeribit()
    app = web.Application()
    app.router.add_get(f"{API_PREFIX}/public/get_index_price", fake.handle)
    async with test_utils.TestServer(app) as server:
        fake.base_url = str(server.make_url(API_PREFIX))
        yield fake


@pytest.fixture
async def http_session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def client(
    fake_deribit: FakeDeribit, http_session: aiohttp.ClientSession
) -> DeribitClient:
    return DeribitClient(
        http_session,
        fake_deribit.base_url,
        timeout=aiohttp.ClientTimeout(total=0.5),
    )


def unused_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_returns_index_price_as_exact_decimal(
    client: DeribitClient, fake_deribit: FakeDeribit
) -> None:
    # через float получилось бы 82153.12345678901
    fake_deribit.body = (
        '{"jsonrpc": "2.0", "result": '
        '{"index_price": 82153.123456789012, "estimated_delivery_price": 1.0}}'
    )

    price = await client.get_index_price(Ticker.BTC_USD)

    assert price == Decimal("82153.123456789012")
    assert isinstance(price, Decimal)
    assert fake_deribit.received_queries == [{"index_name": "btc_usd"}]


async def test_accepts_integer_index_price(
    client: DeribitClient, fake_deribit: FakeDeribit
) -> None:
    fake_deribit.body = '{"result": {"index_price": 2500}}'

    assert await client.get_index_price(Ticker.ETH_USD) == Decimal("2500")


async def test_error_field_in_response_raises(
    client: DeribitClient, fake_deribit: FakeDeribit
) -> None:
    fake_deribit.body = (
        '{"jsonrpc": "2.0", "error": {"code": 10028, "message": "too_many_requests"}}'
    )

    with pytest.raises(DeribitClientError, match="too_many_requests"):
        await client.get_index_price(Ticker.BTC_USD)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, '{"error": {"code": -32602, "message": "Invalid params"}}'),
        (503, "<html>Service Unavailable</html>"),
    ],
)
async def test_non_2xx_status_raises(
    client: DeribitClient, fake_deribit: FakeDeribit, status: int, body: str
) -> None:
    fake_deribit.status = status
    fake_deribit.body = body

    with pytest.raises(DeribitClientError, match=f"HTTP {status}"):
        await client.get_index_price(Ticker.BTC_USD)


async def test_network_error_raises(http_session: aiohttp.ClientSession) -> None:
    client = DeribitClient(http_session, f"http://127.0.0.1:{unused_local_port()}")

    with pytest.raises(DeribitClientError, match="failed") as exc_info:
        await client.get_index_price(Ticker.BTC_USD)

    assert isinstance(exc_info.value.__cause__, aiohttp.ClientError)


async def test_timeout_raises(client: DeribitClient, fake_deribit: FakeDeribit) -> None:
    fake_deribit.delay_seconds = 1

    with pytest.raises(DeribitClientError, match="timed out") as exc_info:
        await client.get_index_price(Ticker.BTC_USD)

    assert isinstance(exc_info.value.__cause__, TimeoutError)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("not a json", id="invalid-json"),
        pytest.param("[1, 2, 3]", id="not-an-object"),
        pytest.param('{"jsonrpc": "2.0"}', id="no-result"),
        pytest.param('{"result": {}}', id="no-index-price"),
        pytest.param('{"result": {"index_price": "82000"}}', id="price-is-string"),
        pytest.param('{"result": {"index_price": true}}', id="price-is-bool"),
        pytest.param('{"result": {"index_price": NaN}}', id="price-is-nan"),
        pytest.param('{"result": {"index_price": 0}}', id="price-is-zero"),
        pytest.param('{"result": {"index_price": -1.5}}', id="price-is-negative"),
    ],
)
async def test_unexpected_format_raises(
    client: DeribitClient, fake_deribit: FakeDeribit, body: str
) -> None:
    fake_deribit.body = body

    with pytest.raises(DeribitClientError):
        await client.get_index_price(Ticker.BTC_USD)
