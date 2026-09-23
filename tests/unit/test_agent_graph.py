import asyncio
import operator
from typing import Annotated, get_args, get_origin, get_type_hints

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph.message import add_messages

from app.services.agent_graph import (
    MAX_ITERATIONS,
    AgentState,
    build_custom_graph,
    custom_graph,
    prebuilt_graph,
    route_after_model,
)


def test_agent_state_contract():
    hints = get_type_hints(AgentState, include_extras=True)
    messages_ann = hints["messages"]
    results_ann = hints["tool_results"]
    assert get_origin(messages_ann) is Annotated
    assert add_messages in get_args(messages_ann)
    assert hints["iteration_count"] is int
    assert get_origin(results_ann) is Annotated
    assert operator.add in get_args(results_ann)
    assert "api_key" not in hints
    assert "client" not in hints


def test_router_stop_and_tools():
    empty = {"messages": [AIMessage(content="готово")], "iteration_count": 1, "tool_results": []}
    assert route_after_model(empty) == "force_finish"
    with_tools = {
        "messages": [AIMessage(content="", tool_calls=[{"name": "get_current_time", "args": {}, "id": "1"}])],
        "iteration_count": 2,
        "tool_results": [],
    }
    assert route_after_model(with_tools) == "execute_tool"
    limited = {**with_tools, "iteration_count": MAX_ITERATIONS}
    assert route_after_model(limited) == "force_finish"


def test_unknown_tool_does_not_crash():
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "not_a_real_tool", "args": {"q": "x"}, "id": "call-unknown"}],
            ),
            AIMessage(content="нет такого инструмента"),
        ]
    )
    graph = build_custom_graph(model=model, tools=[], max_iterations=MAX_ITERATIONS)

    async def _run():
        return await graph.ainvoke(
            {
                "messages": [HumanMessage(content="вызови неизвестный tool")],
                "iteration_count": 0,
                "tool_results": [],
            }
        )

    result = asyncio.run(_run())
    contents = [getattr(m, "content", "") for m in result["messages"]]
    assert any("unknown tool" in str(c) for c in contents)


def test_broken_tool_hits_iteration_cap():
    @tool
    def broken_search(query: str) -> str:
        """Всегда бесполезный ответ. Для проверки стоп-крана."""
        return "пусто"

    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "broken_search", "args": {"query": "x"}, "id": f"loop-{i}"}],
            )
            for i in range(MAX_ITERATIONS + 2)
        ]
    )
    graph = build_custom_graph(model=model, tools=[broken_search], max_iterations=MAX_ITERATIONS)

    async def _run():
        return await graph.ainvoke(
            {
                "messages": [HumanMessage(content="ищи пока не найдёшь")],
                "iteration_count": 0,
                "tool_results": [],
            }
        )

    result = asyncio.run(_run())
    assert result["iteration_count"] == MAX_ITERATIONS
    texts = " ".join(str(getattr(m, "content", "")) for m in result["messages"])
    assert "Превышен лимит итераций" in texts


def test_graphs_compile():
    assert custom_graph.get_graph() is not None
    assert prebuilt_graph.get_graph() is not None
    mermaid = custom_graph.get_graph().draw_mermaid()
    assert "call_model" in mermaid
    assert "execute_tool" in mermaid
    assert "force_finish" in mermaid
