# Персистентный агент и HIL (ДЗ 6.4)

Дата: 31 августа 2026. `agent_graph.py` из 6.3 не менялся — in-memory вариант для тестов графа.  
Новый модуль: `app/services/agent_persistent.py`. Опасное действие — заглушка `send_telegram_message` (print, не Bot API).

## 1. Backend

| Режим | Где | Зачем |
|-------|-----|--------|
| `sqlite` (дефолт) | локальный venv, файл `var/agent_checkpoints.sqlite` | разработка, SSE, тесты на диске |
| `postgres` | сервис `app` в `compose.yaml` (`AGENT_CHECKPOINTER=postgres`) | переживает рестарт контейнера, те же `chat_user` / `chat_db` |
| `memory` | `InMemorySaver` | отладка без файлов |

Переключатель — env `AGENT_CHECKPOINTER`. `setup()` вызывается один раз в FastAPI lifespan, не на каждый HTTP-запрос. Схему чекпоинтера ведёт `setup()`, доменную — Alembic (`include_name` в `alembic/env.py` не даёт autogenerate снести `checkpoints*`).

На Windows `AsyncPostgresSaver` падает на ProactorEventLoop (`psycopg.InterfaceError`). Локально поэтому sqlite; postgres проверялся sync-`setup()` + `\dt`. В Docker (Linux) async-saver штатный.

## 2. Postgres в compose

Новая БД не заводилась. Тот же сервис `postgres:16-alpine`, URI как у чата: `postgresql://chat_user:***@localhost:5432/chat_db` (для LangGraph убирается `+asyncpg`).  
`python scripts/setup_agent_postgres.py`, затем:

```
docker compose exec -T postgres psql -U chat_user -d chat_db -c "\dt"
```

Появились `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations` рядом с `chats` / `chat_messages`.

## 3. Опасный tool и идемпотентность

Взят `send_telegram_message`: исходящее посетителю нельзя отправлять без подтверждения (музейный аналог send_email). Реальный Telegram API не вызывается.

**До interrupt** (`prepare_send_telegram`): вытащить `chat_id`/`text` из tool_call, записать `draft`, `request_id=thread_id` (не uuid). Side-effect нет. Повтор узла даёт тот же draft.

**После interrupt** (`confirm_and_execute_send_telegram`): `decision = interrupt({preview, type: approve_send_telegram})`. Если True — вызвать заглушку и `sent=True`. Если False — `sent=False`, API не звать. Interrupt перезапускает узел с начала, поэтому print/API только после `interrupt()`.

Между узлами обязательное ребро `prepare → confirm`. `interrupt_before` не используется.

## 4. Interrupt и resume

Вывод `python scripts/time_travel_demo.py` (sqlite `:memory:`, без Polza):

```
=== 1. interrupt payload ===
value: {'preview': {'chat_id': '12345', 'text': 'музей открыт 10–18', 'request_id': 'demo-history'}, 'type': 'approve_send_telegram'}
next: ('confirm_and_execute_send_telegram',)
sent: False
```

После `Command(resume=True)` на другом thread: `sent=True`, mock вызван. После `Command(resume=False)`: `sent=False`, mock не вызван.

Curl того же сценария с живой моделью: `docs/agent-stream-curl.log`. После resume в статусе `sent: true`, `__interrupt__: []`.

## 5. Time travel

История `demo-history` (новые → старые):

| checkpoint_id (сокр.) | next | sent |
|-----------------------|------|------|
| …8002-b5b8… | confirm_and_execute_send_telegram | False |
| …8001-e12a… | prepare_send_telegram | False |
| …8000-99c2… | call_model | False |
| …bfff-137e… | __start__ | None |

Чтение прошлого id `…8002-b5b8…`: `next=confirm`, `sent=False`, draft уже готов — до side-effect.

Две ветки с **одинаковым входом и разными thread_id** (`demo-approve` / `demo-reject`): повторный resume того же thread с другим bool не создаёт развилку — значение уже в pending-write. Approve: `sent=True`, mock=1. Reject: `sent=False`, mock=0.

## 6. Streaming

`POST /agent/stream`, `astream(stream_mode=["updates", "messages"])`.

- `updates` — узлы (`call_model`, `prepare_send_telegram`) и `__interrupt__`.
- `messages` — токены LLM после одобрения (в отчётном curl они есть).
- Финальный кадр `status` с `next` / `sent` / `__interrupt__`, чтобы паузу было видно без разбора внутренностей LangGraph.

`astream_events(v2)` не брали: больше шума (`on_chat_model_stream` на каждый токен tool-args), для ДЗ достаточно `astream`. Полный лог: `docs/agent-stream-curl.log`.

`thread_id` приходит в теле запроса (`demo-curl-1`), uuid на запрос не генерируется.

## 7. Permission policy

`configurable.user_role`: `read-only` — черновик есть, отправка всегда отказ без interrupt; `write-with-approve` — interrupt и ждать человека; `full` — interrupt пропускается, заглушка вызывается сразу.

## 8. Что хрупко

- На Windows локальный `AGENT_CHECKPOINTER=postgres` ломается на ProactorEventLoop; нужен sqlite или Linux/Docker.
- `messages` в SSE очень подробный на tool-call streaming; пустые чанки отфильтрованы, но режим всё равно шумный.
- Resume детерминирован по thread: «передумать» после True нельзя без нового `thread_id` или fork через `update_state`.
- Бот к `/agent/stream` не подключён (в ДЗ достаточно curl).
- Checkpointer sqlite-файл живёт в `var/`; его не коммитить.

Тесты: `pytest tests/test_agent_persistent.py` — 3/3 на `AsyncSqliteSaver(":memory:")`, без Postgres.
