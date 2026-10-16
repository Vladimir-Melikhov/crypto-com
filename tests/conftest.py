import pytest

from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Настройки без чтения локального .env."""
    return Settings(
        _env_file=None,
        postgres_user="test_user",
        postgres_password="test_password",
        postgres_db="test_db",
        redis_url="redis://redis-test:6379/0",
    )
