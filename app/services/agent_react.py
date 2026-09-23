"""ReAct-агент с лимитами и Reflexion-light. Baseline 6.1 не трогаем."""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Callable

import structlog
from openai import APITimeoutError, OpenAI

from app.core.config import get_settings
from app.services.agent_naive import DISPATCH
from app.services.rag_common import make_sync_http_client

log = structlog.get_logger()

SYSTEM = (
    "Действовать как агент: самостоятельно выбирать инструменты и их порядок, "
    "при необходимости разбивая задачу на подзадачи. "
    "На каждом шаге сначала одним предложением пояснять, что и зачем делается, "
    "затем вызывать ровно один инструмент и опираться на его результат. "
    "Как только данных достаточно — дать финальный ответ без вызова инструментов. "
    "Не выдумывать данные: использовать только то, что вернули инструменты; "
    "если доступными инструментами задачу решить нельзя — прямо сообщить об этом. "
    "Не вызывай несуществующие tools. "
    "send_telegram_message — только если явно даны chat_id и текст."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Что: возвращает один фрагмент из базы музеев Казанского Кремля. "
                "Когда: нужны часы, билеты, правила, телефоны из документов. "
                "Аргумент query — конкретный вопрос на русском. "
                "Не вызывать для стихов, приветствий и тем вне музея."
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
                "Что: текущие дата и время через zoneinfo, без сети. "
                "Когда: в задаче есть «сейчас», «уже открыто», нужна метка времени. "
                "Аргумент timezone — IANA, по умолчанию Europe/Moscow. "
                "Не вызывать, чтобы узнать часы работы музея — это search_knowledge_base."
            ),
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_telegram_message",
            "description": (
                "Что: учебная заглушка исходящего сообщения (print, не Telegram API). "
                "Когда: пользователь явно назвал chat_id и готовый текст. "
                "Аргументы chat_id и text обязательны. "
                "Не вызывать «на всякий случай» и не выдумывать получателя."
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


def _client(timeout_sec: float) -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=make_sync_http_client(settings),
        timeout=timeout_sec,
        max_retries=0,
    )


def _add_usage(bucket: dict, usage) -> None:
    if usage is None:
        return
    bucket["prompt"] += int(getattr(usage, "prompt_tokens", 0) or 0)
    bucket["completion"] += int(getattr(usage, "completion_tokens", 0) or 0)
    bucket["total"] += int(getattr(usage, "total_tokens", 0) or 0)


def _run_tool(name: str, raw_args: str, dispatch: dict[str, Callable[..., Any]]) -> str:
    try:
        args = json.loads(raw_args or "{}")
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError:
        args = {}
    func: Callable[..., Any] | None = dispatch.get(name)
    if func is None:
        return f"нет такого tool: {name}"
    try:
        return str(func(**args))
    except TypeError as exc:
        return f"плохие аргументы: {exc}"


def _critic(client: OpenAI, model: str, task: str, observation: str, usage: dict) -> str:
    prompt = (
        f"Задача: {task}\nНаблюдение tool:\n{observation[:800]}\n\n"
        "Вердикт одной строкой: OK если наблюдение полезно и можно продолжать или отвечать. "
        "Иначе REVISE: <краткая причина>. Не вызывай tools."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    _add_usage(usage, response.usage)
    return (response.choices[0].message.content or "OK").strip()


def run_react_with_reflection(
    question: str,
    tools: list[dict] | None = None,
    tool_dispatch: dict[str, Callable[..., Any]] | None = None,
    max_iterations: int = 10,
    timeout_per_iteration_sec: float = 15.0,
    max_revisions: int = 2,
    model_main: str | None = None,
    model_critic: str | None = None,
) -> dict:
    if max_iterations >= 30:
        raise ValueError("max_iterations must be < 30")
    settings = get_settings()
    model_main = model_main or settings.openai.default_model
    model_critic = model_critic or settings.openai.default_model
    tools = tools or TOOLS
    dispatch = tool_dispatch if tool_dispatch is not None else DISPATCH
    client = _client(timeout_per_iteration_sec)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    revisions_used = 0
    usage_total = {"prompt": 0, "completion": 0, "total": 0}
    trace: list[dict] = []
    try:
        for step in range(max_iterations):
            t0 = time.monotonic()
            try:
                response = client.chat.completions.create(
                    model=model_main,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
            except APITimeoutError:
                log.info("react.timeout", step=step + 1)
                return {
                    "answer": "Timeout",
                    "usage": usage_total,
                    "steps": step + 1,
                    "revisions": revisions_used,
                    "trace": trace,
                    "error": "Timeout",
                }
            _add_usage(usage_total, response.usage)
            message = response.choices[0].message
            messages.append(message.model_dump())
            calls = message.tool_calls or []
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            if not calls:
                answer = (message.content or "").strip()
                log.info("react.done", step=step + 1, tokens=usage_total["total"])
                return {
                    "answer": answer,
                    "usage": usage_total,
                    "steps": step + 1,
                    "revisions": revisions_used,
                    "trace": trace,
                }
            primary = calls[0]
            observation = _run_tool(primary.function.name, primary.function.arguments or "{}", dispatch)
            messages.append(
                {"role": "tool", "tool_call_id": primary.id, "content": observation}
            )
            for extra in calls[1:]:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": extra.id,
                        "content": "на шаге разрешён только один tool, вызов пропущен",
                    }
                )
            if time.monotonic() - t0 > timeout_per_iteration_sec:
                return {
                    "answer": "Timeout",
                    "usage": usage_total,
                    "steps": step + 1,
                    "revisions": revisions_used,
                    "trace": trace,
                    "error": "Timeout",
                }
            verdict = "OK"
            try:
                verdict = _critic(client, model_critic, question, observation, usage_total)
            except APITimeoutError:
                verdict = "OK"
            if verdict.upper().startswith("REVISE") and revisions_used < max_revisions:
                revisions_used += 1
                messages.append(
                    {
                        "role": "system",
                        "content": f"Критика шага {step + 1}: {verdict}. Исправь план на следующем шаге.",
                    }
                )
            row = {
                "step": step + 1,
                "tool_name": primary.function.name,
                "tool_args": primary.function.arguments,
                "observation": observation[:200],
                "verdict": verdict[:200],
                "latency_ms": latency_ms,
                "prompt_tokens": usage_total["prompt"],
                "completion_tokens": usage_total["completion"],
            }
            trace.append(row)
            log.info(
                "react.step",
                step=step + 1,
                tool=primary.function.name,
                latency_sec=round(time.monotonic() - t0, 2),
                tokens=usage_total["total"],
                verdict=verdict[:80],
            )
        return {
            "answer": "Превышен лимит итераций",
            "usage": usage_total,
            "steps": max_iterations,
            "revisions": revisions_used,
            "trace": trace,
            "error": "Превышен лимит итераций",
        }
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    result = run_react_with_reflection(args.task)
    print(result.get("answer") or "")
    if args.trace:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
