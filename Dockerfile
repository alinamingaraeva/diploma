# syntax=docker/dockerfile:1.7

# ---- Стадия builder ----
FROM python:3.12-slim-bookworm AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PYTHON=/usr/local/bin/python

COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /uvx /bin/

WORKDIR /app

# Создаём виртуальное окружение в /app/.venv
RUN uv venv /app/.venv

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости в venv с кешированием
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /app/.venv/bin/python -r requirements.txt

# Копируем весь код приложения
COPY . .

# ---- Стадия runtime ----
FROM python:3.12-slim-bookworm

# Создаём непривилегированного пользователя
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

# Копируем всё приложение (включая .venv) из builder
COPY --from=builder --chown=appuser:appuser /app /app

# Переключаемся на пользователя
USER appuser

# Добавляем .venv/bin в PATH, чтобы uvicorn был доступен
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]