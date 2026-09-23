# ИИ-консультант музеев Казанского Кремля

Telegram-бот и FastAPI-backend: часы, билеты, телефоны, правила, маршрут по музеям-заповедника Казанский Кремль. Ответы **только по материалам музея**: меняющиеся сведения бот читает на официальном сайте `kazan-kremlin.ru`, постоянные — в локальной базе. Если факта нет ни в одном источнике — отказ: «по базе не нашёл, могу эскалировать».

Курс: «ИИ-разработчик: от API до агентов», модули 3–6.  
Бот в Telegram: `@KazanKremlinBot` (токен в `.env`, в репозиторий не кладётся).

Демонстрация для ИА: видео 5–7 минут (ссылка появится после записи). Живой бот с домашнего ПК на весь период проверки не обещаем.

## Сценарии использования

1. Посетитель в Telegram может сразу написать вопрос без кнопок. Выставки, афиша и вопросы «сегодня / сейчас / в эти выходные» проверяются на официальном сайте; постоянные сведения сопровождаются цитатами из документов.
2. Кнопки меню «Часы / Билеты / Афиша» — готовый текст **без** языковой модели (запас, если LLM недоступен).
3. Вопрос вне базы («кто чемпион мира 2018?») — отказ, без выдуманных фактов.
4. Админ (`BOT_ADMIN_IDS`): `/stats`, `/users`, `/broadcast`.
5. Агент (отдельно от бота): поиск по базе → при необходимости «отправить в чат» только после подтверждения человека (`POST /agent/stream`).

Примеры вопросов для проверки:

- Какой телефон визит-центра Казанского Кремля?
- Можно ли пройти на территорию с собакой?
- Сколько стоит взрослый билет в Музей естественной истории?
- Кто стал чемпионом мира по футболу 2018 года — по документам музея? *(ожидается отказ)*
- Агент: «Найди правила входа с собакой и подготовь сообщение в чат 12345» → пауза на подтверждение, затем заглушка отправки (print, не Bot API).

## Архитектура

```mermaid
flowchart LR
  USER["Посетитель Telegram"] --> BOT["Бот aiogram тонкий клиент"]
  BOT -->|"SSE /chats"]| API["FastAPI ChatService"]
  API --> MOD["Модерация + фильтр выхода"]
  API --> HIST["История JSONL или Postgres"]
  API --> LIVE["Официальный сайт kazan-kremlin.ru"]
  API --> RAG["RAG Qdrant rag_eval_1024 — резерв и постоянные сведения"]
  RAG --> LLM["Polza gpt-4o-mini"]
  API --> AGENT["Агент LangGraph HIL"]
```

Бот не хранит историю и не вызывает модель. Подробности и ADR: [docs/architecture.md](docs/architecture.md). Итоговые решения (что выбрано / из чего / почему): [docs/decisions.md](docs/decisions.md). Ограничения: [docs/limitations.md](docs/limitations.md).

## Запуск

Минимум для RAG-чата (без круглосуточного бота):

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
docker compose up -d qdrant
uvicorn app.main:app --reload
```

Полный стек одной командой: `docker compose up -d --build` (или `docker compose -f docker-compose.yml up -d --build`).

Telegram-бот — отдельный процесс, только когда нужна демонстрация:

```bash
python -m bot
```

После работы: `docker compose stop`. Бот остановить `Ctrl+C`. Контейнеры с `restart: unless-stopped` сами не поднимутся, если их остановили явно.

Тесты одной командой (без живого ключа Polza, с моками):

```bash
pytest tests app/tests -q --basetemp=var/pytest
```

Контрольный прогон 22.09.2026 после добавления живого поиска по официальному сайту: **83 passed**. Отдельные контрактные тесты репозиториев выполнены с запущенным PostgreSQL: **12 passed**, варианты `json` и `postgres` прошли без `skip`.

Оценка RAG (платно по токенам, уже посчитана в отчёте): цифры в [docs/rag_evaluation.md](docs/rag_evaluation.md).

## Переменные окружения

Шаблон: `.env.example`. Живой `.env` в git не входит. Значения ниже — заглушки.

| Переменная | Зачем | Пример заглушки |
|------------|--------|-----------------|
| `OPENAI__API_KEY` | Ключ Polza / OpenAI-совместимого API | `sk-...` |
| `OPENAI__BASE_URL` | Адрес API | `https://api.polza.ai/v1` |
| `OPENAI__DEFAULT_MODEL` | Модель ответа | `openai/gpt-4o-mini` |
| `HTTP_PROXY` | Прокси до LLM, пусто если не нужен | *(пусто)* |
| `REDIS_URL` | Кеш ответов | `redis://localhost:6379/0` |
| `CHAT_REPOSITORY` | История: файлы или БД | `json` |
| `DATABASE_URL` | Postgres для чата и checkpoint агента | `postgresql+asyncpg://chat_user:chat_pass@localhost:5432/chat_db` |
| `BOT_TOKEN` | Токен Telegram | *(пусто)* |
| `BACKEND_URL` | Откуда бот зовёт API | `http://localhost:8000` |
| `BOT_ADMIN_IDS` | Telegram id админов | `[]` |
| `INTERNAL_TOKEN` / `ADMIN_TOKEN` | Бэкенд→бот `/notify` и админка | `change-me-internal` |
| `EMBEDDING_MODEL` | Векторы документов | `openai/text-embedding-3-small` |
| `QDRANT_URL` | Векторная база | `http://localhost:6333` |
| `RAG_COLLECTION` | Боевой индекс | `rag_eval_1024` |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | Нарезка | `1024` / `64` |
| `RAG_RETRIEVE_K` / `RAG_SIMILARITY_TOP_K` | Поиск / в генерацию | `24` / `5` |
| `RAG_SCORE_THRESHOLD` | Отказ, если похожесть ниже | `0.38` |
| `AGENT_CHECKPOINTER` | Память агента | `sqlite` |
| `PHOENIX_COLLECTOR_ENDPOINT` | Трейсы | `http://localhost:4317` |

Полный список — в `.env.example`.

## Документация

- [docs/decisions.md](docs/decisions.md) — обоснование решений для ИА
- [docs/architecture.md](docs/architecture.md) — слои, ADR, сбои
- [docs/rag.md](docs/rag.md) — корпоративный RAG
- [docs/rag_evaluation.md](docs/rag_evaluation.md) — RAGAS, A/B, цифры
- [docs/agent-graph-report.md](docs/agent-graph-report.md) и схема [docs/agent-graph-custom.mmd](docs/agent-graph-custom.mmd)
- [docs/agent-persistent-report.md](docs/agent-persistent-report.md) — HIL и checkpoint
- [docs/multi-agent-report.md](docs/multi-agent-report.md) — почему не несколько агентов
- [docs/limitations.md](docs/limitations.md) — где система не работает
- [docs/data_inventory.md](docs/data_inventory.md) — корпус
- [docs/embeddings.md](docs/embeddings.md), [docs/vector_store.md](docs/vector_store.md), [docs/chunking_experiment.md](docs/chunking_experiment.md)
- [scripts/benchmark_results.md](scripts/benchmark_results.md) — реальный async-бенчмарк ДЗ 3.3
- [docs/security/garak_baseline_2026-09-18.md](docs/security/garak_baseline_2026-09-18.md) и [docs/security/garak_after_2026-09-18.md](docs/security/garak_after_2026-09-18.md) — реальные прогоны Garak ДЗ 3.8
- [Финальная презентация](Финальная%20защита/Презентация-ИА-финальная-2026-09-21.pptx) — 12 слайдов, включая схему архитектуры

## Function calling (ДЗ 3.1)

Инструменты запасного контура (не основной путь свободного текста): `get_opening_hours`, `get_ticket_link`, `search_museum_info` — файл `data/museum_kb.json`.

```bash
python -m examples.run_tool_call
```

Фактический прогон 18.09.2026, модель `openai/gpt-4o-mini` через Polza:

1. `До скольких сегодня работают музеи Казанского Кремля?` — модель вызвала `get_opening_hours` с аргументами `{}`. Обработчик прочитал актуальный `data/museum_kb.json`; после второго запроса модель перечислила основные часы и правило закрытия касс за 30 минут. Суммарно 1195 токенов.
2. `Привет! Кто ты?` — инструмент не вызван. Модель сразу представилась музейным ИИ-консультантом и перечислила допустимые темы. 590 токенов.
3. `Хочу сходить в Кремль, подскажи с чего начать` — пограничный случай решён без инструмента: модель предложила выбрать музей/выставку и уточнить часы и билеты. 603 токена.

Полный цикл подтверждён: `input → tool_call → чтение JSON → role=tool → финальный ответ`; отдельный тест валидирует параметры всех tools через `jsonschema`.
