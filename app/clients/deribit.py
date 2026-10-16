import json
import logging
from decimal import Decimal
from typing import Any

import aiohttp

from app.tickers import Ticker

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10)
INDEX_PRICE_PATH = "/public/get_index_price"
ERROR_BODY_PREVIEW_LENGTH = 200


class DeribitClientError(Exception):
    """Ошибка при обращении к Deribit."""


class DeribitClient:
    """Клиент публичного HTTP API Deribit.

    Сессия aiohttp передаётся снаружи, закрывает её тот, кто создал.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def get_index_price(self, ticker: Ticker) -> Decimal:
        """Возвращает текущую индексную цену тикера.

        Raises:
            DeribitClientError: если запрос не удался или в ответе нет цены.
        """
        payload = await self._get(INDEX_PRICE_PATH, {"index_name": ticker.value})
        price = self._extract_index_price(payload)
        logger.debug("Fetched index price %s = %s", ticker.value, price)
        return price

    async def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.get(
                url, params=params, timeout=self._timeout
            ) as response:
                status = response.status
                body = await response.text()
        except TimeoutError as exc:
            raise DeribitClientError(f"Request to {path} timed out") from exc
        except aiohttp.ClientError as exc:
            raise DeribitClientError(f"Request to {path} failed: {exc!r}") from exc

        if not 200 <= status < 300:
            preview = body[:ERROR_BODY_PREVIEW_LENGTH]
            raise DeribitClientError(
                f"Request to {path} returned HTTP {status}: {preview}"
            )

        try:
            # Числа сразу парсятся в Decimal, без промежуточного float
            payload = json.loads(body, parse_float=Decimal)
        except json.JSONDecodeError as exc:
            raise DeribitClientError(f"Response from {path} is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise DeribitClientError(f"Response from {path} is not a JSON object")
        if "error" in payload:
            raise DeribitClientError(f"Deribit API error: {payload['error']}")
        return payload

    @staticmethod
    def _extract_index_price(payload: dict[str, Any]) -> Decimal:
        result = payload.get("result")
        if not isinstance(result, dict):
            raise DeribitClientError(f"Unexpected response format: {payload}")

        price = result.get("index_price")
        # bool тоже является int, его отсекаем отдельно
        if isinstance(price, bool) or not isinstance(price, int | Decimal):
            raise DeribitClientError(f"Unexpected index_price value: {price!r}")

        price = Decimal(price)
        if price <= 0:
            raise DeribitClientError(f"Invalid index_price value: {price}")
        return price
