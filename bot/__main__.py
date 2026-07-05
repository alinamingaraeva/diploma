import asyncio
import logging
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
from bot.config import get_bot_settings
from bot.services.backend_client import BackendClient
from bot.handlers import commands, text, fsm, media
from bot.web import build_api

logging.basicConfig(level=logging.INFO)

async def main():
    settings = get_bot_settings()

    # Прокси для Telegram
    proxy_url = "http://local_user:p32kcF26NhWE@72.56.89.38:8888"
    # или socks5://...
    session = AiohttpSession(proxy=proxy_url)
    bot = Bot(token=settings.bot_token, session=session)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    backend_client = BackendClient(base_url=settings.backend_url, timeout=settings.backend_timeout)
    dp["backend"] = backend_client

    dp.include_router(commands.router)
    dp.include_router(text.router)
    dp.include_router(fsm.router)
    dp.include_router(media.router)

    # Запускаем API для /notify
    api = build_api(bot, settings.internal_token)
    config = uvicorn.Config(api, host="0.0.0.0", port=settings.bot_api_port, log_level="info")
    server = uvicorn.Server(config)

    # Запускаем polling и API параллельно
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve()
    )

if __name__ == "__main__":
    asyncio.run(main())