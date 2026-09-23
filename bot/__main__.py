import asyncio
import logging

import httpx
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import get_bot_settings
from bot.handlers import admin, commands, feedback, fsm, media, text
from bot.services.backend_client import BackendClient
from bot.web import build_api

logging.basicConfig(level=logging.INFO)


async def main():
    settings = get_bot_settings()
    session = AiohttpSession(proxy=settings.proxy) if settings.proxy else None
    bot = Bot(token=settings.bot_token, session=session)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    timeout = httpx.Timeout(connect=3.0, read=60.0, write=10.0, pool=5.0)
    http = httpx.AsyncClient(timeout=timeout, trust_env=False)
    backend_client = BackendClient(
        base_url=settings.backend_url,
        admin_token=settings.admin_token,
        timeout=settings.backend_timeout,
        http=http,
    )
    dp["backend"] = backend_client

    dp.include_router(commands.router)
    dp.include_router(admin.router)
    dp.include_router(fsm.router)
    dp.include_router(text.router)
    dp.include_router(media.router)
    dp.include_router(feedback.router)

    api = build_api(bot, settings.internal_token)
    config = uvicorn.Config(api, host="0.0.0.0", port=settings.bot_api_port, log_level="info")
    server = uvicorn.Server(config)
    try:
        await asyncio.gather(dp.start_polling(bot), server.serve())
    finally:
        await http.aclose()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
