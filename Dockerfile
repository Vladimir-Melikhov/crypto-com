FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости ставятся отдельным слоем, чтобы он кэшировался
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN groupadd --system appuser \
    && useradd --system --gid appuser --no-create-home appuser

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
