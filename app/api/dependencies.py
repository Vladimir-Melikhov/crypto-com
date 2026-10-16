from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.price import PriceRepository
from app.services.price import PriceQueryService

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


@dataclass(frozen=True, slots=True)
class Pagination:
    """Параметры пагинации."""

    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Период в UNIX timestamp (секунды), границы включительно."""

    start: int | None
    end: int | None


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Открывает сессию БД на время запроса."""
    session_factory: async_sessionmaker[AsyncSession] = (
        request.app.state.session_factory
    )
    async with session_factory() as session:
        yield session


def get_price_query_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PriceQueryService:
    """Создаёт сервис чтения цен."""
    return PriceQueryService(PriceRepository(session))


def get_pagination(
    limit: Annotated[
        int,
        Query(ge=1, le=MAX_PAGE_SIZE, description="Максимум записей в ответе."),
    ] = DEFAULT_PAGE_SIZE,
    offset: Annotated[
        int,
        Query(ge=0, description="Сколько записей пропустить."),
    ] = 0,
) -> Pagination:
    """Читает параметры пагинации из query."""
    return Pagination(limit=limit, offset=offset)


def get_time_range(
    start: Annotated[
        int | None,
        Query(
            ge=0,
            description="Начало периода, UNIX timestamp в секундах (включительно).",
            examples=[1792130000],
        ),
    ] = None,
    end: Annotated[
        int | None,
        Query(
            ge=0,
            description="Конец периода, UNIX timestamp в секундах (включительно).",
            examples=[1792140000],
        ),
    ] = None,
) -> TimeRange:
    """Читает период из query и проверяет, что start не больше end."""
    if start is not None and end is not None and start > end:
        # Тот же формат ответа 422, что и у остальных ошибок валидации
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "start"),
                    "msg": "start must be less than or equal to end",
                    "input": start,
                }
            ]
        )
    return TimeRange(start=start, end=end)


PriceQueryServiceDep = Annotated[PriceQueryService, Depends(get_price_query_service)]
PaginationDep = Annotated[Pagination, Depends(get_pagination)]
TimeRangeDep = Annotated[TimeRange, Depends(get_time_range)]
