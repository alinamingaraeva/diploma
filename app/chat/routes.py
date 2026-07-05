import json
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.chat.deps import get_chat_service
from app.chat.service import ChatService
from pydantic import BaseModel
from app.chat.deps import get_repository


router = APIRouter(prefix="/chats", tags=["chat"])

class CreateChatIn(BaseModel):
    owner_external_id: str
    interface: str
    system_prompt: str | None = None

class CreateChatOut(BaseModel):
    chat_id: UUID

# ---- Создание чата ----
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

# ---- Отправка сообщения (multipart) ----
@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: UUID,
    content: str = Form(...),
    media: UploadFile | None = File(None),
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    async def event_generator():
        async for chunk in chat_service.send_message(chat_id, content, media):
            yield f"data: {json.dumps({'type': 'token', 'delta': chunk})}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ---- Получение истории ----
@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: UUID,
    limit: int = 50,
    chat_service: ChatService = Depends(get_chat_service),
):
    messages = await chat_service.get_history(chat_id, limit)
    return messages

# ---- Очистка истории ----
@router.delete("/{chat_id}/messages")
async def clear_messages(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
):
    await chat_service.clear_history(chat_id)
    return {"status": "ok"}

# ---- Получение метаданных чата ----
@router.get("/{chat_id}")
async def get_chat(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
):
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat
class FeedbackIn(BaseModel):
    message_id: str
    value: str  # 'up' или 'down'
    owner_external_id: str

@router.post("/feedback")
async def save_feedback(
    data: FeedbackIn,
    repo=Depends(get_repository),
):
    # Здесь нужно сохранить фидбек в БД
    # Если используете JSON-репозиторий, можно сохранять в отдельный файл
    # Для PostgreSQL – используем FeedbackRow
    # Пока заглушка
    return {"ok": True}