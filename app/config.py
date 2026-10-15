from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения и .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str
    postgres_password: str
    postgres_db: str

    redis_url: str = "redis://localhost:6379/0"

    deribit_base_url: str = "https://www.deribit.com/api/v2"
    deribit_timeout_seconds: float = Field(default=10.0, gt=0)

    price_collection_interval_seconds: float = Field(default=60.0, gt=0)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @property
    def database_url(self) -> str:
        """DSN для SQLAlchemy с async-драйвером asyncpg."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Возвращает настройки, прочитанные один раз за процесс."""
    return Settings()
