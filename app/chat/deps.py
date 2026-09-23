from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.service import ChatService
from app.core.config import get_settings
from app.deps.providers import get_llm_service


@lru_cache
def _pg_sessionmaker():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_repository():
    settings = get_settings()
    if settings.chat_repository == "json":
        yield JsonChatRepository(base_dir=settings.chat_storage_dir)
        return
    if settings.chat_repository == "postgres":
        from app.chat.repositories.pg_repo import PostgresChatRepository

        async with _pg_sessionmaker()() as session:
            yield PostgresChatRepository(session)
        return
    raise ValueError(f"Unknown repository: {settings.chat_repository}. Use json or postgres.")


def get_chat_service(
    request: Request,
    repo=Depends(get_repository),
    llm=Depends(get_llm_service),
):
    canary = getattr(request.app.state, "canary", "")
    rag = getattr(request.app.state, "rag_service", None)
    return ChatService(repo, llm, get_settings(), canary=canary, rag_service=rag)
