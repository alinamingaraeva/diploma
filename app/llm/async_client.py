import asyncio
import time
from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from structlog import get_logger

logger = get_logger(__name__)


class AsyncLLMClient:
    """Async-клиент с Semaphore, batch и streaming (ДЗ 3.3)."""

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str,
        concurrency: int = 5,
        timeout_sec: float = 15.0,
    ):
        self.openai = openai_client
        self.model = model
        self._concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)
        self.timeout_sec = timeout_sec

    async def complete(self, prompt: str) -> str:
        start = time.perf_counter()
        async with self._sem:
            try:
                async with asyncio.timeout(self.timeout_sec):
                    resp = await self.openai.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                    )
                text = resp.choices[0].message.content or ""
                status = "ok"
            except Exception as exc:
                text = ""
                status = type(exc).__name__
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                logger.info(
                    "llm.call",
                    duration_ms=round(duration_ms, 1),
                    model=self.model,
                    prompt_chars=len(prompt),
                    status=status if "status" in dir() else "error",
                )
        return text

    async def batch_chat(self, prompts: list[str], concurrency: int = 5) -> list[str | Exception]:
        # Semaphore создаётся один раз в __init__. Если запрошен меньший лимит,
        # батч режется на волны; локальный Semaphore намеренно не создаётся.
        wave_size = max(1, min(concurrency, self._concurrency))
        results: list[str | Exception] = []
        for start in range(0, len(prompts), wave_size):
            wave = prompts[start : start + wave_size]
            results.extend(await asyncio.gather(*[self.complete(p) for p in wave], return_exceptions=True))
        return results

    async def stream_chat(self, prompt: str) -> AsyncIterator[str]:
        async with self._sem:
            stream = await self.openai.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                stream_options={"include_usage": True},
            )
            total_tokens = None
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                if chunk.usage:
                    total_tokens = chunk.usage.total_tokens
            logger.info("llm.stream_done", model=self.model, total_tokens=total_tokens)
