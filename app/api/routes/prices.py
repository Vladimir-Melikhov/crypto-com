from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import PaginationDep, PriceQueryServiceDep, TimeRangeDep
from app.api.schemas import PriceRead
from app.tickers import Ticker

TickerQuery = Annotated[
    Ticker,
    Query(description="Тикер валюты.", examples=["btc_usd"]),
]

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get(
    "",
    summary="Все сохранённые цены по валюте",
    description="Цены тикера по возрастанию времени, с пагинацией.",
)
async def get_prices(
    ticker: TickerQuery,
    pagination: PaginationDep,
    service: PriceQueryServiceDep,
) -> list[PriceRead]:
    prices = await service.get_all(
        ticker, limit=pagination.limit, offset=pagination.offset
    )
    return [PriceRead.model_validate(price) for price in prices]


@router.get(
    "/latest",
    summary="Последняя цена валюты",
    responses={status.HTTP_404_NOT_FOUND: {"description": "По тикеру ещё нет цен."}},
)
async def get_latest_price(
    ticker: TickerQuery,
    service: PriceQueryServiceDep,
) -> PriceRead:
    price = await service.get_latest(ticker)
    if price is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No prices found for ticker {ticker.value}",
        )
    return PriceRead.model_validate(price)


@router.get(
    "/by-date",
    summary="Цены валюты с фильтром по дате",
    description=(
        "Цены тикера за период от start до end (UNIX timestamp в секундах), "
        "по возрастанию времени. Обе границы необязательны."
    ),
)
async def get_prices_by_date(
    ticker: TickerQuery,
    time_range: TimeRangeDep,
    pagination: PaginationDep,
    service: PriceQueryServiceDep,
) -> list[PriceRead]:
    prices = await service.get_by_period(
        ticker,
        start=time_range.start,
        end=time_range.end,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return [PriceRead.model_validate(price) for price in prices]
