from decimal import Decimal

from sqlalchemy import BigInteger, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Price(Base):
    """Цена индекса валюты на момент времени."""

    __tablename__ = "prices"
    __table_args__ = (Index("ix_prices_ticker_timestamp", "ticker", "timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16))
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    timestamp: Mapped[int] = mapped_column(BigInteger)
