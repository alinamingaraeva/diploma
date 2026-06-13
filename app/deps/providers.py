from functools import lru_cache
from typing import Annotated
from fastapi import Request, Depends
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.core.config import get_settings, Settings
from app.services.llm import LLMService

# Типы-алиасы для аннотаций
SettingsDep = Annotated[Settings, Depends(get_settings)]

async def get_openai_client(request: Request) -> AsyncOpenAI:
    # Клиент хранится в app.state, инициализируется в lifespan
    return request.app.state.openai_client

OpenAIDep = Annotated[AsyncOpenAI, Depends(get_openai_client)]

async def get_redis_client(request: Request) -> Redis | None:
    # Может быть None, если Redis не подключён
    return getattr(request.app.state, "redis_client", None)

CacheDep = Annotated[Redis | None, Depends(get_redis_client)]

async def get_llm_service(
    openai: OpenAIDep,
    cache: CacheDep,
    settings: SettingsDep,
) -> LLMService:
    return LLMService(openai_client=openai, redis_client=cache, settings=settings)

LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]