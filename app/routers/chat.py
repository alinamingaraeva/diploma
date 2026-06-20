import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatRequest, ChatResponse, ChatDelta
from app.deps.providers import LLMServiceDep
from app.services.security.input_validator import validate_input
from app.services.security.output_filter import filter_output

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse, summary="Синхронный чат")
async def chat_complete(
    chat_request: ChatRequest,
    fastapi_request: Request,
    llm_service: LLMServiceDep
):
    # Валидация входа
    user_message = chat_request.messages[-1].content if chat_request.messages else ""
    validation = validate_input(user_message)
    if not validation.ok:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "input_rejected", "message": validation.reason}}
        )

    # Вызов LLM
    response = await llm_service.complete(chat_request)

    # Фильтр выхода
    try:
        canary = fastapi_request.app.state.canary if hasattr(fastapi_request.app.state, 'canary') else ""
        filtered_content = filter_output(
            response.content,
            system_prompt="",
            canary=canary
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