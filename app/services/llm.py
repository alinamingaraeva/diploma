import hashlib
import json
import time
from typing import AsyncIterator, Optional
from openai import AsyncOpenAI
from redis.asyncio import Redis
from structlog import get_logger

from app.core.exceptions import LLMRateLimitError, LLMTimeoutError, LLMAuthError, LLMProviderError
from app.schemas.chat import ChatRequest, ChatResponse, ChatDelta, Usage
from app.observability.pii import redact_pii, prompt_hash

logger = get_logger(__name__)

class LLMService:
    def __init__(self, openai_client: AsyncOpenAI, redis_client: Optional[Redis], settings):
        self.openai = openai_client
        self.redis = redis_client
        self.settings = settings

    def _get_cache_key(self, request: ChatRequest) -> str:
        exclude = {"user_id", "session_id", "stream"}
        data = request.model_dump(exclude=exclude, exclude_none=True)
        json_str = json.dumps(data, sort_keys=True)
        return f"chat:{hashlib.sha256(json_str.encode()).hexdigest()}"

    async def complete(self, request: ChatRequest) -> ChatResponse:
        start_time = time.perf_counter()
        cached = False
        if self.redis:
            cache_key = self._get_cache_key(request)
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                logger.info(f"Cache hit for key {cache_key}")
                try:
                    response = ChatResponse.model_validate_json(cached_data)
                    response.cached = True
                    # Логируем кешированный ответ
                    logger.info(
                        "llm_request_completed",
                        model=response.model,
                        cached=True,
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        total_tokens=response.usage.total_tokens,
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        finish_reason=response.finish_reason,
                        prompt_hash=prompt_hash(request.messages[0].content if request.messages else ""),
                        prompt_preview=redact_pii(request.messages[0].content if request.messages else "")[:120],
                    )
                    return response
                except Exception as e:
                    logger.warning(f"Failed to parse cached data: {e}")

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
            error_type = type(e).__name__
            if "RateLimit" in error_type:
                raise LLMRateLimitError(str(e))
            elif "Timeout" in error_type:
                raise LLMTimeoutError(str(e))
            elif "Authentication" in error_type:
                raise LLMAuthError(str(e))
            else:
                raise LLMProviderError(str(e))

        response = ChatResponse.from_openai(openai_response, model=model, cached=False)

        if self.redis:
            cache_key = self._get_cache_key(request)
            await self.redis.setex(cache_key, self.settings.cache_ttl_seconds, response.model_dump_json())

        latency_ms = (time.perf_counter() - start_time) * 1000
        # Логируем успешный вызов LLM
        logger.info(
            "llm_request_completed",
            model=response.model,
            cached=False,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            latency_ms=latency_ms,
            finish_reason=response.finish_reason,
            prompt_hash=prompt_hash(request.messages[0].content if request.messages else ""),
            prompt_preview=redact_pii(request.messages[0].content if request.messages else "")[:120],
        )
        return response

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatDelta]:
        start_time = time.perf_counter()
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
                    usage = chunk.usage
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    logger.info(
                        "llm_request_completed",
                        model=model,
                        cached=False,
                        input_tokens=usage.prompt_tokens,
                        output_tokens=usage.completion_tokens,
                        total_tokens=usage.total_tokens,
                        latency_ms=latency_ms,
                        finish_reason="stop",   # в стриме может не быть finish_reason, ставим по умолчанию
                        prompt_hash=prompt_hash(request.messages[0].content if request.messages else ""),
                        prompt_preview=redact_pii(request.messages[0].content if request.messages else "")[:120],
                    )
                    yield ChatDelta(usage=Usage(**usage.model_dump()))
        except Exception as e:
            error_type = type(e).__name__
            if "RateLimit" in error_type:
                raise LLMRateLimitError(str(e))
            elif "Timeout" in error_type:
                raise LLMTimeoutError(str(e))
            elif "Authentication" in error_type:
                raise LLMAuthError(str(e))
            else:
                raise LLMProviderError(str(e))