import hashlib
import json
import logging
from typing import AsyncIterator, Optional, Dict, Any
import asyncio
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.exceptions import LLMRateLimitError, LLMTimeoutError, LLMAuthError, LLMProviderError
from app.schemas.chat import ChatRequest, ChatResponse, ChatDelta, Usage

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self, openai_client: AsyncOpenAI, redis_client: Optional[Redis], settings):
        self.openai = openai_client
        self.redis = redis_client
        self.settings = settings

    def _get_cache_key(self, request: ChatRequest) -> str:
        """Генерирует ключ кеша на основе запроса (исключая user_id, session_id, stream)"""
        exclude = {"user_id", "session_id", "stream"}
        data = request.model_dump(exclude=exclude, exclude_none=True)
        # сортируем для стабильности
        json_str = json.dumps(data, sort_keys=True)
        return f"chat:{hashlib.sha256(json_str.encode()).hexdigest()}"

    async def complete(self, request: ChatRequest) -> ChatResponse:
        # 1. Проверяем кеш (если Redis доступен)
        cached = False
        if self.redis:
            cache_key = self._get_cache_key(request)
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for key {cache_key}")
                try:
                    response = ChatResponse.model_validate_json(cached_data)
                    response.cached = True
                    return response
                except Exception as e:
                    logger.warning(f"Failed to parse cached data: {e}")

        # 2. Вызов OpenAI
        model = request.model or self.settings.openai.default_model
        try:
            openai_response = await self.openai.chat.completions.create(
                model=model,
                messages=[msg.model_dump() for msg in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=False,
            )
        except Exception as e:
            # Преобразуем ошибки OpenAI в доменные
            error_type = type(e).__name__
            if "RateLimit" in error_type:
                raise LLMRateLimitError(str(e))
            elif "Timeout" in error_type:
                raise LLMTimeoutError(str(e))
            elif "Authentication" in error_type:
                raise LLMAuthError(str(e))
            else:
                raise LLMProviderError(str(e))

        # 3. Создаём ответ
        response = ChatResponse.from_openai(openai_response, model=model, cached=False)

        # 4. Сохраняем в кеш (если Redis доступен)
        if self.redis and not cached:
            cache_key = self._get_cache_key(request)
            await self.redis.setex(cache_key, self.settings.cache_ttl_seconds, response.model_dump_json())

        return response

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatDelta]:
        """Генерирует дельты и финальный usage"""
        model = request.model or self.settings.openai.default_model
        try:
            stream = await self.openai.chat.completions.create(
                model=model,
                messages=[msg.model_dump() for msg in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield ChatDelta(content=chunk.choices[0].delta.content)
                if chunk.usage:
                    yield ChatDelta(usage=Usage(**chunk.usage.model_dump()))
        except Exception as e:
            # Та же обработка ошибок
            error_type = type(e).__name__
            if "RateLimit" in error_type:
                raise LLMRateLimitError(str(e))
            elif "Timeout" in error_type:
                raise LLMTimeoutError(str(e))
            elif "Authentication" in error_type:
                raise LLMAuthError(str(e))
            else:
                raise LLMProviderError(str(e))