from typing import AsyncIterator, Optional, List
from uuid import UUID
from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository
from app.chat.context import build_context, count_tokens, fit_to_budget
from app.schemas.chat import ChatRequest, Message
import logging

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, repository: ChatRepository, llm_client, settings):
        self.repo = repository
        self.llm = llm_client
        self.settings = settings

    async def create_chat(self, owner_external_id: str, interface: str, system_prompt: Optional[str] = None) -> Chat:
        return await self.repo.create_chat(owner_external_id, interface, system_prompt)

    async def send_message(self, chat_id: UUID, user_content: str) -> AsyncIterator[str]:
        # 1. Сохраняем сообщение пользователя
        user_msg = ChatMessage(chat_id=chat_id, role="user", content=user_content)
        await self.repo.append_message(chat_id, user_msg)

        # 2. Загружаем чат и историю
        chat = await self.repo.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")
        history = await self.repo.list_messages(chat_id, limit=100)

        # 3. Строим контекст (список словарей role/content)
        messages = build_context(chat, history, strategy=self.settings.chat_context_strategy)

        # 4. Применяем токен-бюджет
        budget = self.settings.model_context_window - self.settings.response_tokens - 200
        messages = fit_to_budget(messages, budget)

        # 5. Создаём ChatRequest для LLMService
        chat_request = ChatRequest(
            messages=[Message(role=m["role"], content=m["content"]) for m in messages],
            model=self.settings.openai.default_model,
            temperature=0.7,
            max_tokens=self.settings.response_tokens,
            stream=True
        )

        # 6. Вызываем LLMService.stream
        full_response = ""
        try:
            async for delta in self.llm.stream(chat_request):
                if delta.content:
                    full_response += delta.content
                    yield delta.content
        except Exception as e:
            logger.error(f"Stream error: {e}")
            # Если стрим оборвался, сохраняем накопленное
            if full_response:
                logger.info("Saving partial response after stream error")
            raise

        # 7. Сохраняем ответ ассистента (если он не пустой)
        if full_response:
            assistant_msg = ChatMessage(chat_id=chat_id, role="assistant", content=full_response)
            await self.repo.append_message(chat_id, assistant_msg)

    async def get_history(self, chat_id: UUID, limit: int = 50) -> List[ChatMessage]:
        return await self.repo.list_messages(chat_id, limit)

    async def clear_history(self, chat_id: UUID) -> None:
        await self.repo.soft_delete_messages(chat_id)

    async def get_chat(self, chat_id: UUID) -> Optional[Chat]:
        return await self.repo.get_chat(chat_id)