from __future__ import annotations

import httpx

from app.core.config import Settings

FALLBACK_ANSWER = "по базе не нашёл, могу эскалировать"

QA_RULES = (
    "Ты консультант музеев Казанского Кремля. Отвечай только по приведённому контексту. "
    "Если ответа в контексте нет — скажи дословно: «по базе не нашёл, могу эскалировать». "
    "Не используй общие знания и не выдумывай телефоны, цены и часы."
)


def qdrant_api_key(settings: Settings) -> str | None:
    if settings.qdrant_api_key is None:
        return None
    return settings.qdrant_api_key.get_secret_value() or None


def make_sync_http_client(settings: Settings) -> httpx.Client:
    timeout = settings.openai.request_timeout
    proxy = settings.http_proxy
    if proxy:
        return httpx.Client(proxy=proxy, trust_env=False, timeout=timeout)
    return httpx.Client(trust_env=False, timeout=timeout)


def make_async_http_client(settings: Settings) -> httpx.AsyncClient:
    timeout = settings.openai.request_timeout
    proxy = settings.http_proxy
    if proxy:
        return httpx.AsyncClient(proxy=proxy, trust_env=False, timeout=timeout)
    return httpx.AsyncClient(trust_env=False, timeout=timeout)


def source_item(text: str, source: str | None, score: float | None) -> dict:
    return {
        "text": (text or "").replace("\r\n", "\n").replace("\r", "\n")[:300],
        "source": source or "unknown",
        "score": round(float(score or 0.0), 3),
    }


def pack_result(answer: str, sources: list[dict], threshold: float) -> dict:
    top_score = max((item.get("score") or 0.0) for item in sources) if sources else 0.0
    top_score = round(float(top_score), 3)
    if top_score < threshold:
        answer = FALLBACK_ANSWER
    return {"answer": answer.strip(), "top_score": top_score, "sources": sources}
