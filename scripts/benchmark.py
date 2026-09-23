"""Бенчмарк sync vs async (ДЗ 3.3)."""
import argparse
import asyncio
import time

import httpx
from openai import AsyncOpenAI, OpenAI

from app.core.config import get_settings
from app.llm.async_client import AsyncLLMClient


def sync_run(prompts: list[str], model: str) -> float:
    settings = get_settings()
    proxy = settings.http_proxy
    http = httpx.Client(proxy=proxy, trust_env=False) if proxy else httpx.Client(trust_env=False)
    client = OpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http,
    )
    start = time.perf_counter()
    for prompt in prompts:
        client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
    elapsed = time.perf_counter() - start
    http.close()
    return elapsed


async def async_run(prompts: list[str], model: str, concurrency: int) -> float:
    settings = get_settings()
    proxy = settings.http_proxy
    http = httpx.AsyncClient(proxy=proxy, trust_env=False) if proxy else httpx.AsyncClient(trust_env=False)
    openai = AsyncOpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http,
    )
    client = AsyncLLMClient(openai, model=model, concurrency=concurrency)
    start = time.perf_counter()
    await client.batch_chat(prompts, concurrency=concurrency)
    elapsed = time.perf_counter() - start
    await openai.close()
    await http.aclose()
    return elapsed


async def stream_run(prompt: str, model: str) -> tuple[float, float, int]:
    """Возвращает TTFT, полное время и число полученных фрагментов."""
    settings = get_settings()
    proxy = settings.http_proxy
    http = httpx.AsyncClient(proxy=proxy, trust_env=False) if proxy else httpx.AsyncClient(trust_env=False)
    openai = AsyncOpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http,
    )
    client = AsyncLLMClient(openai, model=model, concurrency=1)
    started = time.perf_counter()
    first_at: float | None = None
    chunks = 0
    async for delta in client.stream_chat(prompt):
        if first_at is None:
            first_at = time.perf_counter()
        if delta:
            chunks += 1
    finished = time.perf_counter()
    await openai.close()
    await http.aclose()
    return (first_at or finished) - started, finished - started, chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--skip-sync", action="store_true")
    args = parser.parse_args()
    model = get_settings().openai.default_model
    prompts = [f"Объясни одним абзацем концепцию №{i} про посещение музея." for i in range(args.n)]
    print(f"model={model} n={args.n}")
    if not args.skip_sync:
        sync_s = sync_run(prompts, model)
        print(f"sync sequential: {sync_s:.2f}s")
    for conc in (1, 5, 10):
        elapsed = asyncio.run(async_run(prompts, model, conc))
        print(f"async concurrency={conc}: {elapsed:.2f}s")
    ttft, total, chunks = asyncio.run(
        stream_run("Объясни в двух предложениях, зачем музею асинхронный чат-бот.", model)
    )
    print(f"stream: ttft={ttft:.2f}s total={total:.2f}s chunks={chunks}")


if __name__ == "__main__":
    main()
