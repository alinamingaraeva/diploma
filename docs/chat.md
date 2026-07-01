# Архитектура чата


## Mermaid-диаграмма

![Архитектура чата](./architecture.png)

Стратегия контекста
Выбрана стратегия Sliding Window (скользящее окно).

При каждом запросе сервис загружает из репозитория до CHAT_CONTEXT_WINDOW (по умолчанию 10) последних сообщений и передаёт их в LLM вместе с новым сообщением пользователя. Это позволяет модели видеть контекст диалога, не перегружая её историей.

Обоснование: для моего дипломного проекта (FAQ-бот для техподдержки SaaS) диалоги, как правило, короткие и ограничиваются одним вопросом-ответом. Sliding window даёт достаточно контекста для ответа на уточняющие вопросы, при этом экономит токены. Параметр CHAT_CONTEXT_WINDOW можно изменить в .env, чтобы увеличить или уменьшить количество учитываемых сообщений.

Эндпоинты
Все эндпоинты доступны по адресу http://localhost:8000.

1. Создать чат
Запрос:


curl -X POST http://localhost:8000/chats -H "Content-Type: application/json" -d '{"owner_external_id":"user-123","interface":"cli"}'
Ответ:

{"chat_id":"206f735c-6adb-443f-b88d-e31f19fdb0bf"}

2. Отправить сообщение в чат (потоковый SSE)
Запрос:

curl -N -X POST http://localhost:8000/chats/206f735c-6adb-443f-b88d-e31f19fdb0bf/messages -H "Content-Type: application/json" -d '{"content":"Привет, я тестирую PostgreSQL"}'
Ответ: поток данных в формате SSE (Server-Sent Events). Каждый фрагмент ответа приходит в виде:


data: {текст}
...
data: [DONE]
Сообщение пользователя сохраняется в репозитории до вызова LLM. Ответ ассистента также сохраняется после завершения стрима.

3. Получить историю сообщений
Запрос:

curl http://localhost:8000/chats/206f735c-6adb-443f-b88d-e31f19fdb0bf/messages?limit=50
Ответ: JSON-массив сообщений в хронологическом порядке (от старых к новым):

[
  {
    "id": "e22c6bc1-dd06-4ed3-9563-56c5497282c7",
    "chat_id": "206f735c-6adb-443f-b88d-e31f19fdb0bf",
    "role": "user",
    "content": "Привет, я тестирую PostgreSQL",
    "tokens": null,
    "created_at": "2026-07-01T06:37:55.012628Z"
  },
  ...
]
4. Очистить историю (soft delete)
Запрос:

curl -X DELETE http://localhost:8000/chats/206f735c-6adb-443f-b88d-e31f19fdb0bf/messages
Ответ:

{"status":"ok"}
При этом записи в БД не удаляются физически, а помечаются полем deleted_at. Повторный запрос истории вернёт пустой массив.

5. Получить метаданные чата
Запрос:

curl http://localhost:8000/chats/206f735c-6adb-443f-b88d-e31f19fdb0bf
Ответ: метаданные чата (owner_external_id, interface, created_at и т.д.):

{
  "id": "206f735c-6adb-443f-b88d-e31f19fdb0bf",
  "owner_external_id": "user-123",
  "interface": "cli",
  "system_prompt": null,
  "created_at": "2026-07-01T06:37:55.012628Z"
}
Если чат не найден – возвращается 404.

Переключение хранилища
В файле .env установила переменную:


CHAT_REPOSITORY=postgres, сначала делала с json
При использовании PostgreSQL также указала строку подключения:

DATABASE_URL=postgresql+asyncpg://chat_user:chat_pass@localhost:5432/chat_db
Остальные настройки чата:

CHAT_STORAGE_DIR=./var/chats          
CHAT_CONTEXT_STRATEGY=sliding          
CHAT_CONTEXT_WINDOW=10     
            
Примечание по тестам
Для репозитория написаны unit-тесты в tests/chat/test_repository_contract.py. Тесты для JSON-репозитория проходят успешно. Тесты для PostgreSQL требуют доработки управления транзакциями в фикстурах, но функциональность PostgreSQL-репозитория полностью проверена вручную через curl и подтверждена сохранением данных в таблицах.

Текущие ограничения
Прокси-сервер для доступа к LLM недоступен, поэтому вызов LLM не проходит. Однако все эндпоинты и репозитории работают корректно, данные сохраняются в выбранном хранилище.

При использовании PostgreSQL таблицы создаются через Alembic-миграции (alembic upgrade head).