"""HIL + sqlite checkpointer без Postgres и без Polza."""

import asyncio
from unittest.mock import AsyncMock

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.services.agent_persistent import build_agent, merge_input


def _fake_model() -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "send_telegram_message",
                        "args": {"chat_id": "12345", "text": "правила входа с собакой"},
                        "id": "call-send-1",
                    }
                ],
            ),
            AIMessage(content="готово"),
        ]
    )


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "user_role": "write-with-approve"}}


def _payload() -> dict:
    return merge_input({"messages": [HumanMessage(content="отправь правила в чат 12345")]})


def test_graph_pauses_on_approve_node():
    async def _run():
        async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
            await saver.setup()
            graph = build_agent(checkpointer=saver, model=_fake_model(), send_fn=AsyncMock())
            config = _config("t-interrupt")
            await graph.ainvoke(_payload(), config)
            snap = await graph.aget_state(config)
            assert "confirm_and_execute_send_telegram" in (snap.next or ())
            assert snap.interrupts
            return snap

    snap = asyncio.run(_run())
    preview = snap.interrupts[0].value
    assert preview["type"] == "approve_send_telegram"
    assert preview["preview"]["chat_id"] == "12345"


def test_resume_true_sets_sent_and_calls_api():
    async def _run():
        mock = AsyncMock(return_value="Сообщение отправлено в 12345")
        async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
            await saver.setup()
            graph = build_agent(checkpointer=saver, model=_fake_model(), send_fn=mock)
            config = _config("t-approve")
            await graph.ainvoke(_payload(), config)
            await graph.ainvoke(Command(resume=True), config)
            snap = await graph.aget_state(config)
            mock.assert_awaited()
            return snap.values.get("sent")

    assert asyncio.run(_run()) is True


def test_resume_false_does_not_call_api():
    async def _run():
        mock = AsyncMock(return_value="ok")
        async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
            await saver.setup()
            graph = build_agent(checkpointer=saver, model=_fake_model(), send_fn=mock)
            config = _config("t-reject")
            await graph.ainvoke(_payload(), config)
            await graph.ainvoke(Command(resume=False), config)
            snap = await graph.aget_state(config)
            mock.assert_not_called()
            return snap.values.get("sent")

    assert asyncio.run(_run()) is False
