"""Общий tool и набор вопросов для single vs multi (ДЗ 6.5)."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.services.rag_common import make_async_http_client, make_sync_http_client

_RAG = None

QUESTIONS = [
    {
        "id": "01_corpus_phone",
        "kind": "корпус",
        "question": "Какой телефон визит-центра Казанского Кремля?",
    },
    {
        "id": "02_corpus_dog",
        "kind": "корпус",
        "question": "Можно ли пройти на территорию Казанского Кремля с собакой? Какие правила?",
    },
    {
        "id": "03_corpus_excursions",
        "kind": "корпус",
        "question": "Какой телефон отдела экскурсий Казанского Кремля?",
    },
    {
        "id": "04_multistep",
        "kind": "многошаговый",
        "question": (
            "Нужны два факта из базы: телефон визит-центра и кратко правила входа с собакой. "
            "Собери оба в одном ответе со ссылками на источники."
        ),
    },
    {
        "id": "05_oob",
        "kind": "вне базы",
        "question": "Кто стал чемпионом мира по футболу 2018 года — по документам музеев Казанского Кремля?",
    },
]


@tool
def search_knowledge_base(query: str) -> str:
    """Ищет до трёх фрагментов в базе музеев Казанского Кремля.
    Вызывать для часов, билетов, правил, телефонов из документов.
    Возвращает нумерованные куски [1], [2] с именем файла. Не вызывать для тем вне музея."""
    global _RAG
    from app.services.rag import RAGService

    if _RAG is None:
        _RAG = RAGService()
        _RAG.build()
    if _RAG._index is None:
        _RAG.build()
    nodes = _RAG._retrieve_nodes(query)
    lines: list[str] = []
    index = 1
    for node in nodes:
        score = float(getattr(node, "score", 0.0) or 0.0)
        if score < _RAG.settings.rag_score_threshold:
            continue
        inner = getattr(node, "node", node)
        meta = dict(getattr(inner, "metadata", None) or {})
        name = meta.get("file_name") or meta.get("source") or "unknown"
        text = _RAG._node_text(node).replace("\n", " ")[:800]
        lines.append(f"[{index}] источник: {name}\n{text}")
        index += 1
        if index > 3:
            break
    return "\n\n".join(lines) if lines else "в базе пусто"


def close_rag() -> None:
    global _RAG
    if _RAG is not None:
        _RAG.close()
        _RAG = None


def make_model() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai.default_model,
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        temperature=0,
        timeout=settings.openai.request_timeout,
        max_retries=settings.openai.max_retries,
        http_client=make_sync_http_client(settings),
        http_async_client=make_async_http_client(settings),
    )


def last_text(messages: list[Any]) -> str:
    for msg in reversed(messages or []):
        if getattr(msg, "type", None) != "ai":
            continue
        content = getattr(msg, "content", "") or ""
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            content = "".join(parts)
        text = str(content).strip()
        if text:
            return text
    return ""


def usage_from_messages(messages: list[Any]) -> tuple[int, int]:
    prompt = completion = calls = 0
    for msg in messages or []:
        if getattr(msg, "type", None) != "ai":
            continue
        meta = getattr(msg, "usage_metadata", None) or {}
        p = int(meta.get("input_tokens") or 0)
        c = int(meta.get("output_tokens") or 0)
        if p or c:
            prompt += p
            completion += c
            calls += 1
            continue
        resp = getattr(msg, "response_metadata", None) or {}
        token_usage = resp.get("token_usage") or resp.get("usage") or {}
        p = int(token_usage.get("prompt_tokens") or 0)
        c = int(token_usage.get("completion_tokens") or 0)
        if p or c:
            prompt += p
            completion += c
            calls += 1
        elif getattr(msg, "content", None) or getattr(msg, "tool_calls", None):
            calls += 1
    return prompt + completion, calls


def has_citation(text: str) -> bool:
    return bool(re.search(r"\[\d+]", text or ""))


def heuristic_quality(question_id: str, answer: str) -> int:
    text = answer or ""
    low = text.lower()
    if question_id == "01_corpus_phone" and "567-80-16" in text:
        return 5
    if question_id == "02_corpus_dog" and ("собак" in low or "проводн" in low):
        return 5
    if question_id == "03_corpus_excursions" and "567-81-42" in text:
        return 5
    if question_id == "04_multistep" and "567-80-16" in text and ("собак" in low or "проводн" in low):
        return 5
    if question_id == "05_oob" and any(
        token in low
        for token in (
            "в базе пусто",
            "не нашёл",
            "не нашел",
            "нет в базе",
            "нет информации",
            "документах нет",
            "в документах музея",
            "по базе не",
        )
    ):
        return 5
    return 0


def judge_quality(question: str, answer: str, model: ChatOpenAI, question_id: str = "") -> int:
    grounded = heuristic_quality(question_id, answer) if question_id else 0
    prompt = (
        "Оцени ответ консультанта музея. Верни строго SCORE:N где N целое от 0 до 5. "
        "5 — факты из документов или честный отказ, если в базе нет. "
        "0 — выдуманные телефоны, чемпионаты, даты.\n\n"
        f"Вопрос: {question}\nОтвет: {answer[:1500]}"
    )
    response = model.invoke([HumanMessage(content=prompt)])
    raw = str(getattr(response, "content", "") or "")
    match = re.search(r"SCORE:\s*([0-5])", raw, re.I)
    judged = int(match.group(1)) if match else 0
    return max(grounded, judged)
