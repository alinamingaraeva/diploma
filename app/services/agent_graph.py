"""LangGraph ReAct: кастомный StateGraph и prebuilt create_agent (ДЗ 6.3)."""

from __future__ import annotations

import argparse
import asyncio
import json
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.core.config import get_settings
from app.services import agent_naive as naive
from app.services.agent_react import SYSTEM
from app.services.rag_common import make_async_http_client, make_sync_http_client

MAX_ITERATIONS = 6


@tool
def search_knowledge_base(query: str) -> str:
    """Что: один фрагмент из базы музеев Казанского Кремля.
    Когда: нужны часы, билеты, правила, телефоны из документов.
    Аргумент query — конкретный вопрос на русском.
    Не вызывать для стихов, приветствий и тем вне музея."""
    return naive.search_knowledge_base(query)


@tool
def get_current_time(timezone: str = "Europe/Moscow") -> str:
    """Что: текущие дата и время через zoneinfo, без сети.
    Когда: в задаче есть «сейчас», «уже открыто», нужна метка времени.
    Аргумент timezone — IANA, по умолчанию Europe/Moscow.
    Не вызывать, чтобы узнать часы работы музея — это search_knowledge_base."""
    return naive.get_current_time(timezone)


@tool
def send_telegram_message(chat_id: str, text: str) -> str:
    """Что: учебная заглушка исходящего сообщения (print, не Telegram API).
    Когда: пользователь явно назвал chat_id и готовый текст.
    Аргументы chat_id и text обязательны.
    Не вызывать «на всякий случай» и не выдумывать получателя."""
    return naive.send_telegram_message(chat_id, text)


TOOLS = [search_knowledge_base, get_current_time, send_telegram_message]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: Annotated[list[dict], operator.add]


def make_chat_model() -> ChatOpenAI:
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


def _tc_get(tc: Any, key: str, default: Any = None) -> Any:
    if isinstance(tc, dict):
        return tc.get(key, default)
    return getattr(tc, key, default)


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", "") or ""
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts).strip()
    return str(content).strip()


def last_ai_text(messages: list[Any]) -> str:
    for msg in reversed(messages or []):
        if getattr(msg, "type", None) != "ai":
            continue
        text = _message_text(msg)
        if text:
            return text
    return ""


def usage_from_messages(messages: list[Any]) -> dict[str, int]:
    prompt = completion = 0
    for msg in messages or []:
        meta = getattr(msg, "usage_metadata", None) or {}
        prompt += int(meta.get("input_tokens") or 0)
        completion += int(meta.get("output_tokens") or 0)
        if meta:
            continue
        resp = getattr(msg, "response_metadata", None) or {}
        token_usage = resp.get("token_usage") or resp.get("usage") or {}
        prompt += int(token_usage.get("prompt_tokens") or 0)
        completion += int(token_usage.get("completion_tokens") or 0)
    return {"prompt": prompt, "completion": completion, "total": prompt + completion}


def route_after_model(state: AgentState) -> Literal["execute_tool", "force_finish"]:
    if int(state.get("iteration_count") or 0) >= MAX_ITERATIONS:
        return "force_finish"
    last = state["messages"][-1] if state.get("messages") else None
    if getattr(last, "tool_calls", None):
        return "execute_tool"
    return "force_finish"


def build_custom_graph(
    model: Any | None = None,
    tools: list | None = None,
    max_iterations: int = MAX_ITERATIONS,
):
    tools = tools if tools is not None else TOOLS
    chat = model or make_chat_model()
    try:
        bound_model = chat.bind_tools(tools)
    except NotImplementedError:
        bound_model = chat

    async def call_model(state: AgentState) -> dict:
        messages = list(state.get("messages") or [])
        if not messages or getattr(messages[0], "type", None) != "system":
            messages = [SystemMessage(content=SYSTEM), *messages]
        response = await bound_model.ainvoke(messages)
        return {
            "messages": [response],
            "iteration_count": int(state.get("iteration_count") or 0) + 1,
        }

    async def execute_tool(state: AgentState) -> dict:
        last = state["messages"][-1]
        by_name = {t.name: t for t in tools}
        new_messages: list[ToolMessage] = []
        new_results: list[dict] = []
        for tc in getattr(last, "tool_calls", None) or []:
            name = str(_tc_get(tc, "name") or "")
            args = _tc_get(tc, "args") or {}
            call_id = str(_tc_get(tc, "id") or "")
            if name not in by_name:
                content = f"error: unknown tool '{name}'"
            else:
                content = str(await by_name[name].ainvoke(args))
            new_messages.append(ToolMessage(content=content, tool_call_id=call_id))
            new_results.append({"name": name, "args": args, "result": content[:500]})
        return {"messages": new_messages, "tool_results": new_results}

    async def force_finish(state: AgentState) -> dict:
        if int(state.get("iteration_count") or 0) < max_iterations:
            return {}
        last = state["messages"][-1] if state.get("messages") else None
        if getattr(last, "tool_calls", None):
            return {"messages": [AIMessage(content="Превышен лимит итераций")]}
        return {}

    def route(state: AgentState) -> Literal["execute_tool", "force_finish"]:
        if int(state.get("iteration_count") or 0) >= max_iterations:
            return "force_finish"
        last = state["messages"][-1] if state.get("messages") else None
        if getattr(last, "tool_calls", None):
            return "execute_tool"
        return "force_finish"

    builder = StateGraph(AgentState)
    builder.add_node("call_model", call_model)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("force_finish", force_finish)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        route_after_model if max_iterations == MAX_ITERATIONS else route,
        {"execute_tool": "execute_tool", "force_finish": "force_finish"},
    )
    builder.add_edge("execute_tool", "call_model")
    builder.add_edge("force_finish", END)
    return builder.compile()


def build_prebuilt_graph(model: Any | None = None, tools: list | None = None):
    return create_agent(
        model=model or make_chat_model(),
        tools=tools if tools is not None else TOOLS,
        system_prompt=SYSTEM,
    )


custom_graph = build_custom_graph()
prebuilt_graph = build_prebuilt_graph()


async def run_custom(question: str, thread_id: str = "custom") -> dict:
    result = await custom_graph.ainvoke(
        {
            "messages": [HumanMessage(content=question)],
            "iteration_count": 0,
            "tool_results": [],
        },
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = result.get("messages") or []
    return {
        "answer": last_ai_text(messages),
        "steps": int(result.get("iteration_count") or 0),
        "tool_results": result.get("tool_results") or [],
        "usage": usage_from_messages(messages),
    }


async def run_prebuilt(question: str, thread_id: str = "prebuilt") -> dict:
    result = await prebuilt_graph.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = result.get("messages") or []
    steps = sum(1 for msg in messages if getattr(msg, "type", None) == "ai")
    return {
        "answer": last_ai_text(messages),
        "steps": steps,
        "tool_results": [],
        "usage": usage_from_messages(messages),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("--prebuilt", action="store_true")
    args = parser.parse_args()
    runner = run_prebuilt if args.prebuilt else run_custom
    result = asyncio.run(runner(args.task))
    print(result.get("answer") or "")
    print(json.dumps({k: v for k, v in result.items() if k != "answer"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
