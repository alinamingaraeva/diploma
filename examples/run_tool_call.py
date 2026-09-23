"""Прогон трёх кейсов function calling (ДЗ 3.1)."""
import asyncio
import httpx
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.llm.client import ToolCallingClient

CASES = [
    ("a_tool_required", "До скольких сегодня работают музеи Казанского Кремля?"),
    ("b_no_tool", "Привет! Кто ты?"),
    ("c_borderline", "Хочу сходить в Кремль, подскажи с чего начать"),
]


async def main() -> None:
    settings = get_settings()
    proxy = settings.http_proxy or None
    http = httpx.AsyncClient(proxy=proxy, trust_env=False) if proxy else httpx.AsyncClient(trust_env=False)
    openai = AsyncOpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http,
    )
    client = ToolCallingClient(openai, settings.openai.default_model)
    try:
        for name, question in CASES:
            print(f"\n=== {name}: {question}")
            result = await client.complete(question, canary="demo")
            print("used_tool:", result["used_tool"], "tool:", result["tool_name"], "args:", result["tool_args"])
            print("tokens:", result["tokens"])
            print("answer:", result["text"][:400])
    finally:
        await openai.close()
        await http.aclose()


if __name__ == "__main__":
    asyncio.run(main())
