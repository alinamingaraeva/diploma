from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/rag", tags=["rag"])


class RagQueryIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    chat_id: str | None = None


class RagSourceOut(BaseModel):
    id: int
    file_name: str
    page: int | str | None = None
    score: float
    snippet: str


class RagQueryOut(BaseModel):
    answer: str
    top_score: float
    confident: bool
    sources: list[RagSourceOut]


@router.post("/query", response_model=RagQueryOut)
async def rag_query(data: RagQueryIn, request: Request) -> RagQueryOut:
    service = getattr(request.app.state, "rag_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="RAG индекс ещё не готов")
    history = None
    if data.chat_id:
        repo = getattr(request.app.state, "chat_repo", None)
        if repo is not None:
            from uuid import UUID

            messages = await repo.list_messages(UUID(data.chat_id), limit=16)
            history = [{"role": item.role, "content": item.content} for item in messages if item.role in {"user", "assistant"}]
    result = await asyncio.to_thread(service.answer, data.question, history)
    return RagQueryOut.model_validate(result)
