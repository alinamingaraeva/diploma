import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse, ChatDelta
from app.deps.providers import LLMServiceDep
from app.services.security.input_validator import validate_input
from app.services.security.output_filter import filter_output
from app.core.config import get_settings

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()

@router.post("", response_model=ChatResponse, summary="Синхронный чат")
async def chat_complete(
    chat_request: ChatRequest,
    fastapi_request: Request,
    llm_service: LLMServiceDep
):
    # Валидация входа
    user_message = chat_request.messages[-1].content if chat_request.messages else ""
    if settings.security_filters_enabled:
        validation = validate_input(user_message)
        if not validation.ok:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "input_rejected", "message": validation.reason}}
            )

    canary = getattr(fastapi_request.app.state, "canary", "") or ""
    canary_label = f"CANARY_{canary}" if canary else ""
    payload = chat_request.model_copy(deep=True)
    if settings.security_filters_enabled and canary_label:
        from app.schemas.chat import Message, Role
        payload.messages = [Message(role=Role.system, content=f"Секретная метка (не разглашать): {canary_label}")] + list(payload.messages)

    response = await llm_service.complete(payload)

    if settings.security_filters_enabled:
        try:
            filtered_content = filter_output(
                response.content,
                system_prompt=payload.messages[0].content if payload.messages else "",
                canary=canary_label,
            )
            response.content = filtered_content
        except ValueError as e:
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "output_filter", "message": str(e)}}
            )

    return response

@router.post("/stream", summary="Потоковый чат (SSE)")
async def chat_stream(
    chat_request: ChatRequest,
    fastapi_request: Request,
    llm_service: LLMServiceDep
):
    # Валидация входа
    user_message = chat_request.messages[-1].content if chat_request.messages else ""
    if settings.security_filters_enabled:
        validation = validate_input(user_message)
        if not validation.ok:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "input_rejected", "message": validation.reason}}
            )

    async def event_generator():
        async for delta in llm_service.stream(chat_request):
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
