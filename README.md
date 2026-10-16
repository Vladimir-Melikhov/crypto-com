# Deribit Index Prices

Сервис раз в минуту получает с биржи [Deribit](https://docs.deribit.com/)
индексные цены `btc_usd` и `eth_usd`, сохраняет их в PostgreSQL и отдаёт через
API на FastAPI.

Для каждой цены сохраняются тикер, цена и время в UNIX timestamp. Сбор цен
выполняет Celery: beat раз в минуту ставит задачу, worker запрашивает цены
асинхронным клиентом на aiohttp и записывает их в базу.

## Стек

Python 3.12, FastAPI, SQLAlchemy 2 (async) + asyncpg, Alembic, PostgreSQL 16,
Celery 5 + Redis, aiohttp, pydantic-settings, pytest, ruff, Docker Compose.

## Структура проекта

```
app/
  clients/deribit.py       клиент Deribit (aiohttp)
  repositories/price.py    запросы к таблице prices
  services/price.py        сбор цен и чтение цен для API
  tasks/celery_app.py      настройка Celery и расписание beat
  tasks/prices.py          задача сбора цен
  api/                     роуты, схемы ответов, зависимости FastAPI
  db/                      модель Price, создание engine и сессий
  config.py                настройки из переменных окружения
  tickers.py               enum поддерживаемых тикеров
  main.py                  создание приложения FastAPI
  worker.py                точка входа для Celery
alembic/                   миграции
tests/                     unit-тесты
```

## Запуск в Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Поднимаются сервисы:

- `db` - PostgreSQL, порт 15432 на хосте;
- `redis` - брокер для Celery, порт 16379 на хосте;
- `api` - применяет миграции и запускает Uvicorn на порту 8000;
- `worker` - Celery worker, выполняет сбор цен;
- `beat` - Celery beat, раз в минуту ставит задачу сбора.

`api` стартует после того, как БД прошла healthcheck. `worker` ждёт, пока
поднимется `api`, чтобы к этому моменту миграции уже были применены.

Проверка:

```bash
docker compose ps
docker compose logs -f worker   # раз в минуту: "Saved 2 index price(s) ..."
```

Swagger: http://localhost:8000/docs. Первые данные появляются примерно через
минуту после запуска.

Остановить: `docker compose down`, вместе с данными: `docker compose down -v`.

Порты 15432 и 16379 выбраны, чтобы не пересекаться с локально установленными
PostgreSQL и Redis. Внутри compose приложение подключается к `db:5432` и
`redis:6379`, эти значения переопределены в `docker-compose.yml`.

## Локальный запуск

Нужен Python 3.12. БД и Redis удобно поднять в Docker.

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

docker compose up -d db redis
python -m alembic upgrade head
```

Дальше в отдельных терминалах:

```bash
python -m uvicorn app.main:create_app --factory --reload
python -m celery -A app.worker:celery_app worker --loglevel=INFO --pool=solo
python -m celery -A app.worker:celery_app beat --loglevel=INFO
```

На macOS worker нужно запускать с `--pool=solo`. Стандартный пул prefork там
создаёт процессы через spawn, и задача падает с
`ValueError: not enough values to unpack (expected 3, got 0)`. В Docker
используется обычный prefork.

### Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `POSTGRES_HOST` | `localhost` | хост PostgreSQL |
| `POSTGRES_PORT` | `5432` | порт PostgreSQL (в `.env.example` 15432) |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | | пользователь, пароль и имя БД, обязательные |
| `REDIS_URL` | `redis://localhost:6379/0` | брокер Celery |
| `DERIBIT_BASE_URL` | `https://www.deribit.com/api/v2` | адрес API Deribit |
| `DERIBIT_TIMEOUT_SECONDS` | `10` | таймаут запроса к бирже |
| `PRICE_COLLECTION_INTERVAL_SECONDS` | `60` | как часто собирать цены |
| `LOG_LEVEL` | `INFO` | уровень логирования API |

## API

Все методы GET, параметр `ticker` обязателен и принимает `btc_usd` или
`eth_usd`.

| Путь | Параметры | Описание |
|---|---|---|
| `/prices` | `ticker`, `limit`, `offset` | все сохранённые цены по валюте |
| `/prices/latest` | `ticker` | последняя цена валюты |
| `/prices/by-date` | `ticker`, `start`, `end`, `limit`, `offset` | цены валюты за период |

- `limit` от 1 до 1000, по умолчанию 100. `offset` от 0.
- `start` и `end` - UNIX timestamp в секундах, границы включаются. Можно
  передать одну границу или не передавать ни одной.
- Списки отсортированы по времени по возрастанию.
- Цена возвращается строкой, timestamp числом.
- На неизвестный или отсутствующий тикер, `start > end` и неверные
  `limit`/`offset` API отвечает 422.

### Все цены по валюте

```bash
curl "http://localhost:8000/prices?ticker=btc_usd&limit=2"
```

```json
[
  {"ticker": "btc_usd", "price": "82067.25000000", "timestamp": 1792138758},
  {"ticker": "btc_usd", "price": "82141.03000000", "timestamp": 1792138836}
]
```

### Последняя цена

```bash
curl "http://localhost:8000/prices/latest?ticker=eth_usd"
```

```json
{"ticker": "eth_usd", "price": "2452.56000000", "timestamp": 1792138852}
```

Если по тикеру ещё нет данных, возвращается 404:

```json
{"detail": "No prices found for ticker eth_usd"}
```

### Цены за период

```bash
curl "http://localhost:8000/prices/by-date?ticker=btc_usd&start=1792138800&end=1792138900"
```

```json
[
  {"ticker": "btc_usd", "price": "82141.03000000", "timestamp": 1792138836},
  {"ticker": "btc_usd", "price": "82142.02000000", "timestamp": 1792138852}
]
```

Перевести дату в timestamp: `date -u -d '2026-10-16 00:00:00' +%s` (Linux) или
`date -u -j -f '%Y-%m-%d %H:%M:%S' '2026-10-16 00:00:00' +%s` (macOS).

### Ошибки

```bash
curl "http://localhost:8000/prices/latest?ticker=doge_usd"
```

```json
{"detail": [{"type": "enum", "loc": ["query", "ticker"],
  "msg": "Input should be 'btc_usd' or 'eth_usd'", "input": "doge_usd",
  "ctx": {"expected": "'btc_usd' or 'eth_usd'"}}]}
```

```bash
curl "http://localhost:8000/prices/by-date?ticker=btc_usd&start=2000&end=1000"
```

```json
{"detail": [{"type": "value_error", "loc": ["query", "start"],
  "msg": "start must be less than or equal to end", "input": 2000}]}
```

## Тесты и линтер

```bash
python -m pytest
python -m ruff check .
```

Для тестов не нужны ни БД, ни доступ в интернет:

- клиент Deribit проверяется на локальном aiohttp-сервере: успешный ответ,
  ошибка в ответе, статус не 2xx, сетевая ошибка, таймаут, неожиданный формат;
- сервис сбора проверяется с фейковыми клиентом и репозиторием, в том числе
  когда цену одного из тикеров получить не удалось;
- API проверяется через `httpx.AsyncClient`, сервис подменяется через
  `app.dependency_overrides`;
- отдельно проверяется конфигурация Celery.

## Design decisions

### Слои

```
api, tasks              точки входа (FastAPI, Celery)
    |
services                логика
    |
clients, repositories   биржа и БД
```

Зависимости идут только сверху вниз. Клиент работает только с биржей,
репозиторий только с БД. Сервис содержит логику и не знает про HTTP и Celery,
поэтому его можно тестировать без сети и базы. API и задача Celery только
создают нужные объекты и вызывают сервис.

### ООП и отсутствие глобальных переменных

Клиент, репозиторий и сервисы сделаны классами, зависимости передаются через
конструктор. Engine БД, сессии и HTTP-сессия не создаются при импорте модулей:

- в API engine создаётся в lifespan и хранится в `app.state`, сессия БД
  открывается на каждый запрос через `Depends`;
- в Celery всё нужное создаётся внутри задачи на каждый запуск.

Настройки читаются функцией `get_settings()` с `lru_cache`. Приложения
создаются фабриками `create_app()` и `create_celery_app()`.

На уровне модулей остались только константы, логгеры, роутеры и экземпляр
Celery в `app/worker.py`. Без последнего не обойтись: Celery CLI (`-A`) умеет
работать только с готовым экземпляром приложения. Этот модуль нигде не
импортируется, а задача объявлена через `shared_task` и от него не зависит.

### Асинхронность

Сервис в основном ждёт ответа от биржи и БД, поэтому выбран асинхронный стек:
aiohttp, SQLAlchemy async с asyncpg, FastAPI. Цены двух тикеров запрашиваются
параллельно через `asyncio.gather`.

### Celery и Redis

Celery требуется по заданию. beat отвечает за расписание, worker выполняет
задачу, и сбор цен работает отдельно от API. Брокером выбран Redis: его проще
всего поднять, а потеря одного запуска раз в минуту некритична. Результаты
задач не хранятся (`task_ignore_result`), данные и так пишутся в PostgreSQL.

У задачи в расписании стоит `expires`, равный интервалу. Если worker какое-то
время не работал, накопившиеся задачи не выполнятся подряд после его запуска
и не запишут несколько почти одинаковых цен за пару секунд.

### Engine создаётся на каждый запуск задачи

Задача Celery синхронная, асинхронный код запускается через `asyncio.run()`,
а он каждый раз создаёт новый event loop. Соединения asyncpg и сессия aiohttp
привязаны к loop, в котором созданы. Если сделать engine общим, следующий
запуск получит из пула соединение от закрытого loop и упадёт. Поэтому engine и
HTTP-сессия создаются в начале задачи и закрываются в `finally`
(`engine.dispose()`). Это одно новое подключение к БД раз в минуту, заметной
нагрузки оно не создаёт.

### Decimal и Numeric вместо float

float хранит числа в двоичном виде и не может точно представить многие
десятичные дроби, для цен это не подходит. Ответ биржи разбирается через
`json.loads(..., parse_float=Decimal)`, в БД цена хранится как
`NUMERIC(20, 8)`.

В ответе API цена отдаётся строкой. Многие клиенты (например, JavaScript)
читают числа из JSON как double и теряют точность, а строку клиент может
преобразовать как ему нужно. Так же цены отдают, например, Binance и Coinbase.

### BigInteger для timestamp

`INTEGER` в PostgreSQL 32-битный и переполнится 19 января 2038 года, поэтому
для timestamp и id используется `BIGINT`.

### Индекс (ticker, timestamp)

Все запросы ищут по тикеру и фильтруют или сортируют по времени. Составной
индекс `(ticker, timestamp)` подходит для всех трёх методов API: все цены по
тикеру, последняя цена и цены за период. Сначала идёт колонка, по которой
ищем на равенство, потом колонка для диапазона.

### Фильтр по дате

`start` и `end` передаются в UNIX timestamp, в том же виде, в каком время
хранится в БД. Так не возникает вопросов с часовыми поясами и форматами дат.
Границы включаются в период, обе необязательны. Если `start` больше `end`,
API возвращает 422 в стандартном формате ошибок FastAPI. У этого метода тоже
есть `limit`/`offset`, чтобы запрос за большой период не выгружал всю таблицу.

### Один timestamp на все цены запуска

Время берётся один раз перед запросами и записывается обоим тикерам. Так цены
`btc_usd` и `eth_usd` из одного запуска легко сопоставить, даже если ответы
пришли в разные моменты. Все цены запуска сохраняются одной транзакцией.

### Ошибки биржи

Все ошибки при обращении к бирже клиент превращает в `DeribitClientError` и
сохраняет исходную причину через `raise ... from exc`: сетевые ошибки,
таймаут, статус не 2xx, поле `error` в ответе, некорректный JSON или цену.
Сервис обрабатывает эту ошибку для каждого тикера отдельно: пишет в лог и
сохраняет остальные цены. Другие исключения не перехватываются, чтобы ошибки в
коде не терялись.

Повторных попыток внутри задачи нет. Следующий запуск будет через минуту, а
цена, полученная с задержкой, уже не относится к нужному моменту.

### Количество контейнеров

В задании предлагается два контейнера: приложение и БД. Celery нужен брокер,
поэтому добавлен Redis. API, worker и beat - это разные процессы, и запускать
их в одном контейнере неудобно: Docker следит за одним процессом, логи
смешиваются, масштабировать сервисы по отдельности нельзя. Поэтому все три
сервиса используют один образ приложения и отличаются только командой
запуска.

beat должен работать в одном экземпляре, иначе задачи будут дублироваться.
worker можно масштабировать: `docker compose up -d --scale worker=3`.

### Что можно улучшить

- уникальный индекс `(ticker, timestamp)` и `INSERT ... ON CONFLICT DO NOTHING`
  для защиты от дублей;
- интеграционные тесты репозитория на настоящем PostgreSQL (testcontainers)
  и CI;
- разделить зависимости на prod и dev, собирать образ в несколько стадий;
- keyset-пагинация вместо offset для больших объёмов данных;
- healthcheck для worker и beat, метрики и алерты на неудачные запуски;
- поддержка дат в формате ISO 8601 в фильтре;
- подписка на индекс через WebSocket API Deribit, если цены понадобится
  обновлять чаще.
