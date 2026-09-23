import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.chat.repositories.json_repo import JsonChatRepository


@pytest_asyncio.fixture(params=["json", "postgres"])
async def repo(request, tmp_path):
    if request.param == "json":
        yield JsonChatRepository(base_dir=tmp_path)
        return
    try:
        engine = create_async_engine(
            "postgresql+asyncpg://chat_user:chat_pass@localhost:5432/chat_db",
            echo=False,
        )
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        from app.chat.repositories.pg_repo import PostgresChatRepository

        async with async_session() as session:
            yield PostgresChatRepository(session)
        await engine.dispose()
    except Exception:
        pytest.skip("Postgres недоступен")
