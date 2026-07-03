import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from bot.config import get_bot_settings
from bot.services.backend_client import BackendClient
from bot.handlers import commands, text, fsm

logging.basicConfig(level=logging.INFO)

async def main():
    settings = get_bot_settings()

    # Прокси (можно http или socks5)
    proxy_url = "socks5://local_user:p32kcF26NhWE@72.56.89.38:1081"
    # Если не работает, попробуйте socks5:
    # proxy_url = "socks5://local_user:p32kcF26NhWE@72.56.89.38:1081"

    # Создаём сессию aiogram с прокси
    session = AiohttpSession(proxy=proxy_url)
    bot = Bot(token=settings.bot_token, session=session)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    backend_client = BackendClient(base_url=settings.backend_url, timeout=settings.backend_timeout)
    dp["backend"] = backend_client

    dp.include_router(commands.router)
    dp.include_router(text.router)
    dp.include_router(fsm.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())