"""Наивный agent loop: Chat Completions + allowlist tools. Без LangGraph."""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from openai import OpenAI

from app.core.config import get_settings
from app.services.rag_common import make_sync_http_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("agent_naive")

_RAG = None

SYSTEM = (
    "Ты агент-консультант музеев Казанского Кремля. "
    "Решай задачу через инструменты: сначала поиск в базе, затем при необходимости отправка в чат. "
    "Не выдумывай факты, телефоны и цены. Не вызывай несуществующие tools. "
    "Если tool вернул пусто или «нет в базе» — так и скажи, не крути цикл вхолостую. "
    "Пишущие действия (send_telegram_message) делай только если в задаче явно указаны chat_id и текст; "
    "иначе сначала уточни. Когда данных достаточно — ответь пользователю без нового tool."
)


def search_knowledge_base(query: str) -> str:
    """Ищет фрагмент в RAG-базе музея Казанского Кремля. Вызывать, когда нужны часы, билеты, правила, телефоны из документов, а не общие знания."""
    global _RAG
    from app.services.rag import RAGService

    if _RAG is None:
        _RAG = RAGService()
        _RAG.build()
    if _RAG._index is None:
        _RAG.build()
    nodes = _RAG._retrieve_nodes(query)
    if not nodes:
        return "в базе пусто"
    text = _RAG._node_text(nodes[0]).replace("\n", " ")[:1200]
    score = float(getattr(nodes[0], "score", 0.0) or 0.0)
    if score < _RAG.settings.rag_score_threshold:
        return f"по базе не нашёл (score={score:.3f})"
    return text


def get_current_time(timezone: str = "Europe/Moscow") -> str:
    """Возвращает текущие дату и время в указанной IANA-зоне. Вызывать, когда в задаче нужны «сейчас», «уже открыто» или сравнение с часами работы."""
    try:
        return datetime.now(ZoneInfo(timezone)).isoformat()
    except Exception as exc:
        return f"ошибка timezone: {exc}"


def send_telegram_message(chat_id: str, text: str) -> str:
    """Печатает заглушку исходящего сообщения посетителю. Вызывать только после явного chat_id и готового текста; реальный Telegram API не вызывается."""
    print(f"[TELEGRAM → {chat_id}] {text}")
    return f"Сообщение отправлено в {chat_id}"


DISPATCH = {
    "search_knowledge_base": search_knowledge_base,
    "get_current_time": get_current_time,
    "send_telegram_message": send_telegram_message,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Ищет один самый релевантный фрагмент в базе знаний музеев Казанского Кремля. "
                "Вызывать для фактов из документов: часы, билеты, правила, телефоны, как добраться."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": (
                "Возвращает текущие дату и время через zoneinfo, без сети. "
                "Вызывать, чтобы понять, открыт ли музей «сейчас», или когда в задаче явно нужна метка времени."
            ),
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string", "default": "Europe/Moscow"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": (
                "Учебная заглушка: печатает текст в консоль как будто сообщение ушло в Telegram. "
                "Вызывать только если пользователь явно дал chat_id и текст; не вызывать «на всякий случай»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_id": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["chat_id", "text"],
                "additionalProperties": False,
            },
        },
    },
]


def _client() -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=make_sync_http_client(settings),
        timeout=settings.openai.request_timeout,
        max_retries=settings.openai.max_retries,
    )


def run_agent(task: str, max_steps: int = 6) -> dict:
    settings = get_settings()
    client = _client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]
    trace: list[dict] = []
    try:
        for step in range(1, max_steps + 1):
            started = time.perf_counter()
            response = client.chat.completions.create(
                model=settings.openai.default_model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            usage = response.usage
            message = response.choices[0].message
            messages.append(message.model_dump())
            calls = message.tool_calls or []
            if not calls:
                answer = (message.content or "").strip()
                log.info("stop step=%s answer=%s", step, answer[:160])
                return {"answer": answer, "steps": step, "trace": trace}
            for call in calls:
                raw_args = call.function.arguments or "{}"
                try:
                    args = json.loads(raw_args)
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                func = DISPATCH.get(call.function.name)
                if func is None:
                    result = f"нет такого tool: {call.function.name}"
                else:
                    try:
                        result = str(func(**args))
                    except TypeError as exc:
                        result = f"плохие аргументы: {exc}"
                row = {
                    "step": step,
                    "tool_name": call.function.name,
                    "tool_args": raw_args,
                    "tool_result": result[:200],
                    "llm_input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                    "llm_output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                    "duration_ms": duration_ms,
                }
                trace.append(row)
                log.info("step=%s tool=%s args=%s", step, call.function.name, raw_args[:180])
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        return {
            "answer": "",
            "steps": max_steps,
            "trace": trace,
            "error": "Превышен лимит шагов",
        }
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--max-steps", type=int, default=6)
    args = parser.parse_args()
    result = run_agent(args.task, max_steps=args.max_steps)
    print(result.get("answer") or result.get("error") or "")
    if args.trace:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
