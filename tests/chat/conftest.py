import pytest_asyncio
from pathlib import Path
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@pytest_asyncio.fixture(params=["json", "postgres"])
async def repo(request, tmp_path):
    if request.param == "json":
        yield JsonChatRepository(base_dir=tmp_path)
    elif request.param == "postgres":
        engine = create_async_engine(
            "postgresql+asyncpg://chat_user:chat_pass@localhost:5432/chat_db",
            echo=False
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        async with async_session() as session:
            async with session.begin():
                yield PostgresChatRepository(session)
            