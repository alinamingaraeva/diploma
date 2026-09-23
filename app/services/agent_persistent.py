"""Персистентный ReAct-граф с HIL. agent_graph.py из 6.3 не трогаем."""

from __future__ import annotations

import operator
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from app.core.config import get_settings
from app.services import agent_naive as naive
from app.services.agent_react import SYSTEM
from app.services.rag_common import make_async_http_client, make_sync_http_client

MAX_ITERATIONS = 6
SEND_TOOL = "send_telegram_message"
DANGEROUS_PREVIEW_TYPE = "approve_send_telegram"


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
    """Что: исходящее сообщение посетителю. Опасное действие: без подтверждения не выполняется.
    Когда: пользователь явно назвал chat_id и готовый текст.
    Аргументы chat_id и text обязательны."""
    return naive.send_telegram_message(chat_id, text)


TOOLS = [search_knowledge_base, get_current_time, send_telegram_message]


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    iteration_count: int
    tool_results: Annotated[list[dict], operator.add]
    draft: dict
    sent: bool
    user_role: str


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


def postgres_dsn(database_url: str) -> str:
    return (
        database_url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


def _tc_get(tc: Any, key: str, default: Any = None) -> Any:
    if isinstance(tc, dict):
        return tc.get(key, default)
    return getattr(tc, key, default)


def _configurable() -> dict:
    try:
        cfg = get_config() or {}
    except RuntimeError:
        cfg = {}
    return dict(cfg.get("configurable") or {})


def _thread_id() -> str:
    return str(_configurable().get("thread_id") or "cli")


def _role(state: AgentState) -> str:
    return str(_configurable().get("user_role") or state.get("user_role") or "write-with-approve")


def _last_ai(state: AgentState) -> Any:
    for msg in reversed(state.get("messages") or []):
        if getattr(msg, "type", None) == "ai":
            return msg
    return None


def _tool_calls(msg: Any) -> list:
    return list(getattr(msg, "tool_calls", None) or [])


def _has_send(msg: Any) -> bool:
    return any(str(_tc_get(tc, "name") or "") == SEND_TOOL for tc in _tool_calls(msg))


def _has_safe_tools(msg: Any) -> bool:
    return any(str(_tc_get(tc, "name") or "") != SEND_TOOL for tc in _tool_calls(msg))


def extract_send_args(state: AgentState) -> tuple[str, str, str]:
    last = _last_ai(state)
    for tc in _tool_calls(last):
        if str(_tc_get(tc, "name") or "") != SEND_TOOL:
            continue
        args = _tc_get(tc, "args") or {}
        return str(args.get("chat_id") or ""), str(args.get("text") or ""), str(_tc_get(tc, "id") or "")
    draft = state.get("draft") or {}
    return str(draft.get("chat_id") or ""), str(draft.get("text") or ""), str(draft.get("tool_call_id") or "")


def empty_state() -> dict:
    return {
        "messages": [],
        "iteration_count": 0,
        "tool_results": [],
        "draft": {},
        "sent": False,
        "user_role": "write-with-approve",
    }


def merge_input(payload: dict | None) -> dict:
    base = empty_state()
    if not payload:
        return base
    merged = {**base, **payload}
    if "messages" in payload and payload["messages"] and not hasattr(payload["messages"][0], "type"):
        merged["messages"] = [
            HumanMessage(content=m["content"]) if isinstance(m, dict) and m.get("role") == "user" else m
            for m in payload["messages"]
        ]
    return merged


def route_after_model(state: AgentState) -> Literal["execute_tool", "prepare_send_telegram", "force_finish"]:
    if int(state.get("iteration_count") or 0) >= MAX_ITERATIONS:
        return "force_finish"
    last = _last_ai(state)
    if _has_safe_tools(last):
        return "execute_tool"
    if _has_send(last):
        return "prepare_send_telegram"
    return "force_finish"


def route_after_tools(state: AgentState) -> Literal["prepare_send_telegram", "call_model"]:
    if _has_send(_last_ai(state)):
        return "prepare_send_telegram"
    return "call_model"


async def _default_send(chat_id: str, text: str) -> str:
    return naive.send_telegram_message(chat_id, text)


def build_agent(
    checkpointer,
    model: Any | None = None,
    send_fn: Callable[..., Any] | None = None,
    max_iterations: int = MAX_ITERATIONS,
):
    tools = TOOLS
    chat = model or make_chat_model()
    try:
        bound_model = chat.bind_tools(tools)
    except NotImplementedError:
        bound_model = chat
    sender = send_fn or _default_send

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
        last = _last_ai(state)
        by_name = {t.name: t for t in tools}
        new_messages: list[ToolMessage] = []
        new_results: list[dict] = []
        for tc in _tool_calls(last):
            name = str(_tc_get(tc, "name") or "")
            if name == SEND_TOOL:
                continue
            args = _tc_get(tc, "args") or {}
            call_id = str(_tc_get(tc, "id") or "")
            if name not in by_name:
                content = f"error: unknown tool '{name}'"
            else:
                content = str(await by_name[name].ainvoke(args))
            new_messages.append(ToolMessage(content=content, tool_call_id=call_id))
            new_results.append({"name": name, "args": args, "result": content[:500]})
        return {"messages": new_messages, "tool_results": new_results}

    async def prepare_send_telegram(state: AgentState) -> dict:
        chat_id, text, call_id = extract_send_args(state)
        request_id = _thread_id()
        draft = {
            "chat_id": chat_id,
            "text": text,
            "tool_call_id": call_id,
            "request_id": request_id,
        }
        return {"draft": draft, "sent": False}

    async def confirm_and_execute_send_telegram(state: AgentState) -> dict:
        draft = dict(state.get("draft") or {})
        role = _role(state)
        preview = {
            "preview": {
                "chat_id": draft.get("chat_id"),
                "text": draft.get("text"),
                "request_id": draft.get("request_id"),
            },
            "type": DANGEROUS_PREVIEW_TYPE,
        }
        if role == "read-only":
            decision = False
        elif role == "full":
            decision = True
        else:
            decision = interrupt(preview)

        call_id = str(draft.get("tool_call_id") or "send")
        if decision:
            result = await sender(str(draft.get("chat_id") or ""), str(draft.get("text") or ""))
            content = str(result)
            sent = True
        else:
            content = "отправка отклонена"
            sent = False
        return {
            "sent": sent,
            "messages": [ToolMessage(content=content, tool_call_id=call_id)],
            "tool_results": [{"name": SEND_TOOL, "args": draft, "result": content[:500]}],
        }

    async def force_finish(state: AgentState) -> dict:
        if int(state.get("iteration_count") or 0) < max_iterations:
            return {}
        last = _last_ai(state)
        if _tool_calls(last):
            return {"messages": [AIMessage(content="Превышен лимит итераций")]}
        return {}

    builder = StateGraph(AgentState)
    builder.add_node("call_model", call_model)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("prepare_send_telegram", prepare_send_telegram)
    builder.add_node("confirm_and_execute_send_telegram", confirm_and_execute_send_telegram)
    builder.add_node("force_finish", force_finish)
    builder.add_edge(START, "call_model")
    builder.add_conditional_edges(
        "call_model",
        route_after_model,
        {
            "execute_tool": "execute_tool",
            "prepare_send_telegram": "prepare_send_telegram",
            "force_finish": "force_finish",
        },
    )
    builder.add_conditional_edges(
        "execute_tool",
        route_after_tools,
        {
            "prepare_send_telegram": "prepare_send_telegram",
            "call_model": "call_model",
        },
    )
    builder.add_edge("prepare_send_telegram", "confirm_and_execute_send_telegram")
    builder.add_edge("confirm_and_execute_send_telegram", "call_model")
    builder.add_edge("force_finish", END)
    return builder.compile(checkpointer=checkpointer)


@asynccontextmanager
async def open_checkpointer():
    settings = get_settings()
    backend = settings.agent_checkpointer
    if backend == "memory":
        yield InMemorySaver()
        return
    if backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        path = settings.agent_sqlite_path
        path.parent.mkdir(parents=True, exist_ok=True)
        async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
            await saver.setup()
            yield saver
        return
    if backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        dsn = postgres_dsn(settings.database_url)
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.setup()
            yield saver
        return
    raise ValueError(f"unknown AGENT_CHECKPOINTER={backend}")


@asynccontextmanager
async def agent_lifespan() -> AsyncIterator:
    async with open_checkpointer() as saver:
        yield build_agent(saver)
