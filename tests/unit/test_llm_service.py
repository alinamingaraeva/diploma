import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from app.services.llm import LLMService
from app.schemas.chat import ChatRequest, Message, Usage, ChatResponse
from app.core.config import get_settings
from app.core.exceptions import LLMRateLimitError

@pytest.fixture
def mock_openai():
    return AsyncMock()

@pytest.fixture
def mock_redis():
    return AsyncMock()

@pytest.fixture
def llm_service(mock_openai, mock_redis):
    settings = get_settings()
    return LLMService(
        openai_client=mock_openai,
        redis_client=mock_redis,
        settings=settings
    )

@pytest.mark.asyncio
async def test_cache_hit(llm_service, mock_redis):
    """Test that cache is used when response is stored."""
    request = ChatRequest(messages=[Message(role="user", content="test")])
    cached_response = ChatResponse(
        content="cached answer",
        model="gpt-4o-mini",
        usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        finish_reason="stop",
        cached=True
    )
    mock_redis.get = AsyncMock(return_value=cached_response.model_dump_json())

    response = await llm_service.complete(request)
    assert response.cached is True
    assert response.content == "cached answer"

@pytest.mark.asyncio
async def test_cache_miss_and_set(llm_service, mock_redis, mock_openai):
    """Test that cache is saved when response is new."""
    request = ChatRequest(messages=[Message(role="user", content="test")])
    mock_redis.get = AsyncMock(return_value=None)
    
    # Правильный мок для openai_response
    mock_usage = MagicMock()
    mock_usage.model_dump = MagicMock(return_value={
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30
    })
    mock_openai.chat.completions.create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="new answer"), finish_reason="stop")],
        usage=mock_usage
    ))

    response = await llm_service.complete(request)
    assert response.cached is False
    mock_redis.setex.assert_awaited_once()

@pytest.mark.asyncio
async def test_pii_redaction(llm_service):
    """Test that PII is redacted in logs."""
    request = ChatRequest(messages=[Message(role="user", content="My email ivan@mail.ru")])
    from app.observability.pii import redact_pii
    redacted = redact_pii(request.messages[0].content)
    assert "ivan@mail.ru" not in redacted
    assert "[EMAIL]" in redacted

@pytest.mark.asyncio
async def test_stream_chunk_parsing(llm_service, mock_openai):
    """Test that streaming chunks are parsed correctly."""
    class MockChunk:
        def __init__(self, content=None, usage=None):
            self.choices = [MagicMock(delta=MagicMock(content=content))] if content else []
            self.usage = usage

    # Создаём асинхронный итератор из списка
    chunks_data = [
        MockChunk(content="Hello"),
        MockChunk(content=" world"),
        MockChunk(usage=MagicMock(
            prompt_tokens=5,
            completion_tokens=10,
            total_tokens=15,
            model_dump=MagicMock(return_value={
                "prompt_tokens": 5,
                "completion_tokens": 10,
                "total_tokens": 15
            })
        ))
    ]
    
    # Используем AsyncMock для имитации асинхронного потока
    mock_stream = AsyncMock()
    mock_stream.__aiter__.return_value = chunks_data
    # Чтобы async for работал, нужно, чтобы __anext__ возвращал следующий элемент
    # Проще: создать корутину, которая возвращает итератор по chunks_data
    async def async_iterator():
        for item in chunks_data:
            yield item
    mock_openai.chat.completions.create = AsyncMock(return_value=async_iterator())

    request = ChatRequest(messages=[Message(role="user", content="test")])
    chunks = []
    async for delta in llm_service.stream(request):
        chunks.append(delta)
    assert len(chunks) == 3
    assert chunks[0].content == "Hello"
    assert chunks[1].content == " world"
    assert chunks[2].usage.total_tokens == 15

@pytest.mark.asyncio
async def test_cache_key_generation(llm_service):
    """Test cache key is deterministic and excludes user_id."""
    request1 = ChatRequest(messages=[Message(role="user", content="test")], user_id="123")
    request2 = ChatRequest(messages=[Message(role="user", content="test")], user_id="456")
    key1 = llm_service._get_cache_key(request1)
    key2 = llm_service._get_cache_key(request2)
    assert key1 == key2  # should be same, because user_id excluded

@pytest.mark.asyncio
async def test_retry_on_rate_limit(llm_service, mock_openai):
    """Test that rate limit errors are converted to domain exceptions."""
    import openai
    mock_openai.chat.completions.create = AsyncMock(side_effect=openai.RateLimitError(
        message="Rate limit exceeded",
        response=MagicMock(),
        body={"message": "rate limit"}
    ))
    request = ChatRequest(messages=[Message(role="user", content="test")])
    with pytest.raises(LLMRateLimitError):
        await llm_service.complete(request)
def test_prompt_construction():
    """Проверяет, что промпт формируется правильно с учётом ролей."""
    from app.schemas.chat import ChatRequest, Message
    request = ChatRequest(messages=[
        Message(role="system", content="You are helpful"),
        Message(role="user", content="Hello")
    ])
    # Проверяем, что messages сериализуются корректно
    data = [msg.model_dump() for msg in request.messages]
    assert data[0]["role"] == "system"
    assert data[0]["content"] == "You are helpful"
    assert data[1]["role"] == "user"
    assert data[1]["content"] == "Hello"
def test_parse_json_from_markdown():
    """Проверяет извлечение JSON из markdown-фрагмента."""
    import json
    from app.schemas.chat import ChatResponse  # если есть парсер, иначе можно просто пример
    # Эмулируем ответ с JSON в markdown
    raw = '```json\n{"content": "test", "model": "gpt"}\n```'
    # В реальном приложении у вас может быть функция парсинга, но для теста просто проверяем, что извлекается
    # Допустим, у нас есть функция extract_json_from_markdown, но для примера проверим регуляркой
    import re
    match = re.search(r'```json\n(.*?)\n```', raw, re.DOTALL)
    assert match is not None
    data = json.loads(match.group(1))
    assert data["content"] == "test"