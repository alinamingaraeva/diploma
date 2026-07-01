import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.chat.deps import get_chat_service
from app.chat.service import ChatService

router = APIRouter(prefix="/chats", tags=["chat"])

class CreateChatIn(BaseModel):
    owner_external_id: str
    interface: str
    system_prompt: str | None = None

class CreateChatOut(BaseModel):
    chat_id: UUID

class MessageIn(BaseModel):
    content: str

@router.post("", response_model=CreateChatOut)
async def create_chat(data: CreateChatIn, service: ChatService = Depends(get_chat_service)):
    chat = await service.create_chat(data.owner_external_id, data.interface, data.system_prompt)
    return CreateChatOut(chat_id=chat.id)

@router.post("/{chat_id}/messages")
async def send_message(chat_id: UUID, data: MessageIn, service: ChatService = Depends(get_chat_service)):
    async def event_generator():
        async for chunk in service.send_message(chat_id, data.content):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/{chat_id}/messages")
async def list_messages(chat_id: UUID, limit: int = 50, service: ChatService = Depends(get_chat_service)):
    return await service.get_history(chat_id, limit)

@router.delete("/{chat_id}/messages")
async def clear_messages(chat_id: UUID, service: ChatService = Depends(get_chat_service)):
    await service.clear_history(chat_id)
    return {"status": "ok"}

@router.get("/{chat_id}")
async def get_chat(chat_id: UUID, service: ChatService = Depends(get_chat_service)):
    chat = await service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat