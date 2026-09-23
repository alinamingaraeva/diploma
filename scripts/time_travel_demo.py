"""Time travel по checkpoint'ам: interrupt, история, прошлый снимок, две ветки."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.services.agent_persistent import build_agent, merge_input

PAYLOAD = merge_input(
    {"messages": [HumanMessage(content="отправь в чат 12345 текст: музей открыт 10–18")]}
)


def _model() -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "send_telegram_message",
                        "args": {"chat_id": "12345", "text": "музей открыт 10–18"},
                        "id": "call-send-demo",
                    }
                ],
            ),
            AIMessage(content="черновик обработан"),
        ]
    )


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id, "user_role": "write-with-approve"}}


async def _graph(saver, mock):
    return build_agent(checkpointer=saver, model=_model(), send_fn=mock)


async def _until_interrupt(graph, thread_id: str):
    await graph.ainvoke(PAYLOAD, _cfg(thread_id))
    return await graph.aget_state(_cfg(thread_id))


async def main() -> None:
    mock = AsyncMock(return_value="Сообщение отправлено в 12345")
    async with AsyncSqliteSaver.from_conn_string(":memory:") as saver:
        await saver.setup()

        print("=== 1. interrupt payload ===")
        graph = await _graph(saver, mock)
        snap = await _until_interrupt(graph, "demo-history")
        for item in snap.interrupts or ():
            print("value:", item.value)
            print("id:", item.id)
        print("next:", snap.next)
        print("sent:", snap.values.get("sent"), "draft:", snap.values.get("draft"))

        print("\n=== 2. aget_state_history ===")
        rows = [s async for s in graph.aget_state_history(_cfg("demo-history"))]
        print(f"{'checkpoint_id':<40} {'next':<40} sent")
        for row in rows[:8]:
            cid = (row.config.get("configurable") or {}).get("checkpoint_id", "")
            print(f"{str(cid):<40} {str(row.next):<40} {row.values.get('sent')}")

        print("\n=== 3. прошлый checkpoint (до отправки) ===")
        past = next((row for row in rows if "confirm_and_execute_send_telegram" in (row.next or ())), None)
        if past is not None:
            old_id = (past.config.get("configurable") or {}).get("checkpoint_id")
            loaded = await graph.aget_state(
                {"configurable": {"thread_id": "demo-history", "checkpoint_id": old_id}}
            )
            print("checkpoint_id:", old_id)
            print("next:", loaded.next)
            print("sent:", loaded.values.get("sent"))
            print("draft:", loaded.values.get("draft"))

        print("\n=== 4. две ветки из одинакового входа (разные thread_id) ===")
        mock_ok = AsyncMock(return_value="Сообщение отправлено в 12345")
        graph_ok = await _graph(saver, mock_ok)
        await _until_interrupt(graph_ok, "demo-approve")
        await graph_ok.ainvoke(Command(resume=True), _cfg("demo-approve"))
        ok = await graph_ok.aget_state(_cfg("demo-approve"))
        print("approve sent=", ok.values.get("sent"), "mock_called=", mock_ok.await_count)

        mock_no = AsyncMock(return_value="ok")
        graph_no = await _graph(saver, mock_no)
        await _until_interrupt(graph_no, "demo-reject")
        await graph_no.ainvoke(Command(resume=False), _cfg("demo-reject"))
        no = await graph_no.aget_state(_cfg("demo-reject"))
        print("reject sent=", no.values.get("sent"), "mock_called=", mock_no.await_count)


if __name__ == "__main__":
    asyncio.run(main())
