from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.tickers import Ticker


class PriceRead(BaseModel):
    """Сохранённая цена валюты."""

    model_config = ConfigDict(from_attributes=True)

    ticker: Ticker = Field(description="Тикер валюты.", examples=["btc_usd"])
    price: Decimal = Field(
        description="Индексная цена. Передаётся строкой, чтобы не терять точность.",
        examples=["82153.93000000"],
    )
    timestamp: int = Field(
        description="Время получения цены, UNIX timestamp в секундах.",
        examples=[1792138758],
    )
