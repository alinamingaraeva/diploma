from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage
from langgraph.types import Command, Interrupt
from pydantic import BaseModel, Field

from app.services.agent_persistent import merge_input

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentStreamIn(BaseModel):
    thread_id: str = Field(min_length=1, max_length=200)
    input: dict[str, Any] | None = None
    resume: bool | None = None
    user_role: Literal["read-only", "write-with-approve", "full"] = "write-with-approve"


def _empty_message_chunk(data: Any) -> bool:
    if not isinstance(data, list) or not data:
        return False
    first = data[0] if isinstance(data[0], dict) else {}
    content = first.get("content") if isinstance(first, dict) else ""
    tools = first.get("tool_calls") if isinstance(first, dict) else None
    has_tools = bool(tools) and any((t or {}).get("name") for t in tools if isinstance(t, dict))
    return not content and not has_tools


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Interrupt):
        return {"id": value.id, "value": _jsonable(value.value)}
    if isinstance(value, BaseMessage):
        return {
            "type": getattr(value, "type", None),
            "content": getattr(value, "content", None),
            "tool_calls": getattr(value, "tool_calls", None),
        }
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return str(value)


@router.post("/stream")
async def agent_stream(body: AgentStreamIn, request: Request) -> StreamingResponse:
    graph = getattr(request.app.state, "agent_graph", None)
    if graph is None:
        raise HTTPException(status_code=503, detail="агентный граф ещё не готов")
    if body.resume is None and not body.input:
        raise HTTPException(status_code=422, detail="нужен input или resume")

    config = {
        "configurable": {
            "thread_id": body.thread_id,
            "user_role": body.user_role,
        }
    }
    payload: Any = Command(resume=body.resume) if body.resume is not None else merge_input(body.input)

    async def events():
        async for mode, chunk in graph.astream(
            payload,
            config,
            stream_mode=["updates", "messages"],
        ):
            data = _jsonable(chunk)
            if mode == "messages" and _empty_message_chunk(data):
                continue
            yield f"data: {json.dumps({'mode': mode, 'data': data}, ensure_ascii=False)}\n\n"
        snapshot = await graph.aget_state(config)
        interrupt_payload = [
            {"id": item.id, "value": _jsonable(item.value)}
            for item in (snapshot.interrupts or ())
        ]
        yield (
            "data: "
            + json.dumps(
                {
                    "mode": "status",
                    "data": {
                        "next": list(snapshot.next or ()),
                        "sent": (snapshot.values or {}).get("sent"),
                        "draft": (snapshot.values or {}).get("draft"),
                        "__interrupt__": interrupt_payload,
                    },
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
