from enum import StrEnum


class Ticker(StrEnum):
    """Поддерживаемые тикеры; значение совпадает с index_name на Deribit."""

    BTC_USD = "btc_usd"
    ETH_USD = "eth_usd"
