from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.api.dependencies import get_price_query_service
from app.config import Settings
from app.db.models import Price
from app.main import create_app
from app.services.price import PriceQueryService
from app.tickers import Ticker

BTC_PRICE = Price(ticker="btc_usd", price=Decimal("82153.93000000"), timestamp=1000)
BTC_PRICE_LATER = Price(
    ticker="btc_usd", price=Decimal("82160.12345678"), timestamp=1060
)
BTC_PRICE_JSON = {"ticker": "btc_usd", "price": "82153.93000000", "timestamp": 1000}
BTC_PRICE_LATER_JSON = {
    "ticker": "btc_usd",
    "price": "82160.12345678",
    "timestamp": 1060,
}

ENDPOINTS = ["/prices", "/prices/latest", "/prices/by-date"]


@pytest.fixture
def query_service() -> AsyncMock:
    return AsyncMock(spec=PriceQueryService)


@pytest.fixture
def app(settings: Settings, query_service: AsyncMock) -> FastAPI:
    # ASGITransport не запускает lifespan, так что engine не создаётся
    app = create_app(settings)
    app.dependency_overrides[get_price_query_service] = lambda: query_service
    return app


@pytest.fixture
async def api_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_get_prices_returns_all_prices_for_ticker(
    api_client: httpx.AsyncClient, query_service: AsyncMock
) -> None:
    query_service.get_all.return_value = [BTC_PRICE, BTC_PRICE_LATER]

    response = await api_client.get("/prices", params={"ticker": "btc_usd"})

    assert response.status_code == 200
    assert response.json() == [BTC_PRICE_JSON, BTC_PRICE_LATER_JSON]
    query_service.get_all.assert_awaited_once_with(Ticker.BTC_USD, limit=100, offset=0)


async def test_get_prices_passes_pagination(
    api_client: httpx.AsyncClient, query_service: AsyncMock
) -> None:
    query_service.get_all.return_value = []

    response = await api_client.get(
        "/prices", params={"ticker": "eth_usd", "limit": 10, "offset": 20}
    )

    assert response.status_code == 200
    assert response.json() == []
    query_service.get_all.assert_awaited_once_with(Ticker.ETH_USD, limit=10, offset=20)


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 1001}, {"offset": -1}],
    ids=["limit-zero", "limit-above-max", "negative-offset"],
)
async def test_get_prices_rejects_invalid_pagination(
    api_client: httpx.AsyncClient, query_service: AsyncMock, params: dict[str, int]
) -> None:
    response = await api_client.get("/prices", params={"ticker": "btc_usd", **params})

    assert response.status_code == 422
    query_service.get_all.assert_not_awaited()


async def test_get_latest_price(
    api_client: httpx.AsyncClient, query_service: AsyncMock
) -> None:
    query_service.get_latest.return_value = BTC_PRICE_LATER

    response = await api_client.get("/prices/latest", params={"ticker": "btc_usd"})

    assert response.status_code == 200
    assert response.json() == BTC_PRICE_LATER_JSON
    query_service.get_latest.assert_awaited_once_with(Ticker.BTC_USD)


async def test_get_latest_price_returns_404_when_no_data(
    api_client: httpx.AsyncClient, query_service: AsyncMock
) -> None:
    query_service.get_latest.return_value = None

    response = await api_client.get("/prices/latest", params={"ticker": "eth_usd"})

    assert response.status_code == 404
    assert response.json() == {"detail": "No prices found for ticker eth_usd"}


async def test_get_prices_by_date_filters_by_period(
    api_client: httpx.AsyncClient, query_service: AsyncMock
) -> None:
    query_service.get_by_period.return_value = [BTC_PRICE]

    response = await api_client.get(
        "/prices/by-date", params={"ticker": "btc_usd", "start": 900, "end": 1000}
    )

    assert response.status_code == 200
    assert response.json() == [BTC_PRICE_JSON]
    query_service.get_by_period.assert_awaited_once_with(
        Ticker.BTC_USD, start=900, end=1000, limit=100, offset=0
    )


@pytest.mark.parametrize(
    ("params", "expected_start", "expected_end"),
    [
        ({}, None, None),
        ({"start": 1000}, 1000, None),
        ({"end": 1000}, None, 1000),
        ({"start": 1000, "end": 1000}, 1000, 1000),
    ],
    ids=["no-bounds", "only-start", "only-end", "single-moment"],
)
async def test_get_prices_by_date_bounds_are_optional(
    api_client: httpx.AsyncClient,
    query_service: AsyncMock,
    params: dict[str, int],
    expected_start: int | None,
    expected_end: int | None,
) -> None:
    query_service.get_by_period.return_value = []

    response = await api_client.get(
        "/prices/by-date", params={"ticker": "btc_usd", **params}
    )

    assert response.status_code == 200
    query_service.get_by_period.assert_awaited_once_with(
        Ticker.BTC_USD, start=expected_start, end=expected_end, limit=100, offset=0
    )


async def test_get_prices_by_date_rejects_start_after_end(
    api_client: httpx.AsyncClient, query_service: AsyncMock
) -> None:
    response = await api_client.get(
        "/prices/by-date", params={"ticker": "btc_usd", "start": 2000, "end": 1000}
    )

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["query", "start"]
    assert error["msg"] == "start must be less than or equal to end"
    query_service.get_by_period.assert_not_awaited()


@pytest.mark.parametrize("path", ENDPOINTS)
async def test_unknown_ticker_returns_422(
    api_client: httpx.AsyncClient, path: str
) -> None:
    response = await api_client.get(path, params={"ticker": "doge_usd"})

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["query", "ticker"]


@pytest.mark.parametrize("path", ENDPOINTS)
async def test_missing_ticker_returns_422(
    api_client: httpx.AsyncClient, path: str
) -> None:
    response = await api_client.get(path)

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["query", "ticker"]
    assert error["type"] == "missing"


async def test_health(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
