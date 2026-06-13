import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse, ChatDelta
from app.deps.providers import LLMServiceDep

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse, summary="Синхронный чат")
async def chat_complete(request: ChatRequest, llm_service: LLMServiceDep):
    """Возвращает полный ответ от LLM (с кешированием)."""
    response = await llm_service.complete(request)
    return response

@router.post("/stream", summary="Потоковый чат (SSE)")
async def chat_stream(request: ChatRequest, llm_service: LLMServiceDep):
    async def event_generator():
        async for delta in llm_service.stream(request):
            if delta.content:
                yield f"data: {json.dumps({'content': delta.content})}\n\n"
            elif delta.usage:
                yield f"data: {json.dumps({'usage': delta.usage.model_dump()})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )