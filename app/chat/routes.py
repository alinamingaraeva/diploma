import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.chat.deps import get_chat_service, get_repository
from app.chat.domain import MessageFeedback
from app.chat.service import ChatService
from app.services.notifier import notify_user

router = APIRouter(prefix="/chats", tags=["chat"])

_MESSAGE_ID_RE = re.compile(r"\[\[message_id:([0-9a-fA-F-]{36})\]\]")
_SOURCES_RE = re.compile(r"^\[\[sources:(.*)\]\]$", re.DOTALL)


def extract_stream_message_id(chunk: str) -> str | None:
    match = _MESSAGE_ID_RE.search(chunk or "")
    return match.group(1) if match else None


def extract_stream_sources(chunk: str) -> str | None:
    match = _SOURCES_RE.match((chunk or "").strip())
    return match.group(1) if match else None


class CreateChatIn(BaseModel):
    owner_external_id: str
    interface: str
    system_prompt: str | None = None


class CreateChatOut(BaseModel):
    chat_id: UUID


class SystemMessageIn(BaseModel):
    text: str
    notify: bool = False


class FeedbackIn(BaseModel):
    value: str = Field(pattern="^(up|down)$")
    owner_external_id: str


@router.post("", response_model=CreateChatOut)
async def create_chat(
    data: CreateChatIn,
    chat_service: ChatService = Depends(get_chat_service),
):
    chat = await chat_service.create_chat(
        data.owner_external_id,
        data.interface,
        data.system_prompt,
    )
    return CreateChatOut(chat_id=chat.id)


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: UUID,
    content: str = Form(...),
    media: UploadFile | None = File(None),
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    async def event_generator():
        async for chunk in chat_service.send_message(chat_id, content, media):
            sources_payload = extract_stream_sources(chunk)
            if sources_payload is not None:
                yield f"event: sources\ndata: {sources_payload}\n\n"
                continue
            message_id = extract_stream_message_id(chunk)
            if message_id:
                yield f"data: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"
                return
            yield f"data: {json.dumps({'type': 'token', 'delta': chunk}, ensure_ascii=False)}\n\n"
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: UUID,
    limit: int = 50,
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.get_history(chat_id, limit)


@router.delete("/{chat_id}/messages")
async def clear_messages(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
):
    await chat_service.clear_history(chat_id)
    return {"status": "ok"}


@router.get("/{chat_id}")
async def get_chat(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
):
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


class FeedbackStandaloneIn(BaseModel):
    message_id: UUID
    value: str = Field(pattern="^(up|down)$")
    owner_external_id: str


@router.post("/feedback")
async def save_feedback_standalone(
    data: FeedbackStandaloneIn,
    repo=Depends(get_repository),
):
    feedback = MessageFeedback(
        message_id=data.message_id,
        owner_external_id=data.owner_external_id,
        value=data.value,  # type: ignore[arg-type]
    )
    await repo.save_feedback(feedback)
    return {"ok": True}


@router.post("/{chat_id}/messages/{message_id}/feedback")
async def save_feedback(
    chat_id: UUID,
    message_id: UUID,
    data: FeedbackIn,
    repo=Depends(get_repository),
):
    feedback = MessageFeedback(
        message_id=message_id,
        owner_external_id=data.owner_external_id,
        value=data.value,  # type: ignore[arg-type]
    )
    await repo.save_feedback(feedback)
    return {"ok": True}


@router.post("/{chat_id}/system-message")
async def system_message(
    chat_id: UUID,
    body: SystemMessageIn,
    chat_service: ChatService = Depends(get_chat_service),
):
    from app.chat.domain import ChatMessage

    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    await chat_service.repo.append_message(
        chat_id,
        ChatMessage(chat_id=chat_id, role="assistant", content=body.text),
    )
    if body.notify:
        try:
            await notify_user(int(chat.owner_external_id), body.text)
        except ValueError:
            raise HTTPException(status_code=400, detail="owner_external_id is not a telegram id")
    return {"ok": True}
