from fastapi import Depends
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import get_settings
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from app.chat.service import ChatService
from app.deps.providers import get_llm_service

def get_repository():
    settings = get_settings()
    if settings.chat_repository == "json":
        return JsonChatRepository(base_dir=settings.chat_storage_dir)
    elif settings.chat_repository == "postgres":
        # Создаём асинхронный движок и фабрику сессий
        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        # Создаём сессию для одного запроса (для простоты)
        session = async_session()
        return PostgresChatRepository(session)
    else:
        raise ValueError(f"Unknown repository: {settings.chat_repository}")

def get_chat_service(
    repo=Depends(get_repository),
    llm=Depends(get_llm_service)
):
    return ChatService(repo, llm, get_settings())