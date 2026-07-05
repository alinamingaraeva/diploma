import time
import logging
import hashlib
from typing import AsyncIterator, Optional, List, Dict, Any
from uuid import UUID
from fastapi import HTTPException, UploadFile
from app.chat.domain import Chat, ChatMessage
from app.chat.repository import ChatRepository
from app.chat.context import build_context, count_tokens, fit_to_budget
from app.chat.media import media_to_part, set_openai_client
from app.moderation.service import ModerationService
from app.schemas.chat import ChatRequest, Message

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self, repository: ChatRepository, llm_client, settings):
        self.repo = repository
        self.llm = llm_client
        self.settings = settings
        # Инициализация модерации
        self.moderation = ModerationService(openai_client=self.llm.openai)
        # Передаём OpenAI клиент в media.py
        set_openai_client(llm_client.openai)

    async def create_chat(self, owner_external_id: str, interface: str, system_prompt: Optional[str] = None) -> Chat:
        return await self.repo.create_chat(owner_external_id, interface, system_prompt)

    async def send_message(
        self,
        chat_id: UUID,
        user_content: str,
        media: Optional[UploadFile] = None
    ) -> AsyncIterator[str]:
        # ---- 1. Модерация входа ----
        mod_result = await self.moderation.check_input(user_content)
        if not mod_result.allowed:
            logger.warning(
                f"input_moderation_blocked: hash={hashlib.sha256(user_content.encode()).hexdigest()[:16]}, "
                f"categories={mod_result.categories}, blocked_by={mod_result.blocked_by}"
            )
            raise HTTPException(
                status_code=403,
                detail={"code": "moderation_blocked", "categories": mod_result.categories}
            )

        # ---- 2. Сохраняем сообщение пользователя ----
        user_msg = ChatMessage(chat_id=chat_id, role="user", content=user_content)
        await self.repo.append_message(chat_id, user_msg)

        # ---- 3. Загружаем чат и историю ----
        chat = await self.repo.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")
        history = await self.repo.list_messages(chat_id, limit=100)

        # ---- 4. Строим контекст ----
        messages = build_context(chat, history, strategy=self.settings.chat_context_strategy)

        # ---- 5. Обработка медиа (если есть) ----
        media_part = None
        if media:
            media_part = await media_to_part(media)
            # Добавляем медиа-часть в последнее сообщение пользователя
            if messages and messages[-1]["role"] == "user":
                # Создаём новый массив content
                content_parts = [
                    {"type": "text", "text": messages[-1]["content"]}
                ]
                if media_part["type"] == "image_url":
                    content_parts.append(media_part)
                else:
                    # Для голоса и документов media_part уже содержит текст
                    content_parts.append({"type": "text", "text": media_part["text"]})
                messages[-1] = {
                    "role": "user",
                    "content": content_parts
                }

        # ---- 6. Формируем список сообщений для OpenAI ----
        openai_messages = []
        for m in messages:
            if isinstance(m["content"], list):
                openai_messages.append({"role": m["role"], "content": m["content"]})
            else:
                openai_messages.append({"role": m["role"], "content": m["content"]})

        # ---- 7. Применяем токен-бюджет (упрощённо) ----
        # Для простоты пропускаем, но можно добавить

        # ---- 8. Вызов LLM и стриминг ----
        start_time = time.perf_counter()
        full_response = ""
        try:
            stream = await self.llm.openai.chat.completions.create(
                model=self.settings.openai.default_model,
                messages=openai_messages,
                stream=True,
                stream_options={"include_usage": True},
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    full_response += delta
                    yield delta
        except Exception as e:
            logger.error(f"Stream error: {e}")
            raise

        latency_ms = (time.perf_counter() - start_time) * 1000

        # ---- 9. Модерация выхода ----
        if full_response:
            mod_output = await self.moderation.check_output(full_response)
            if not mod_output.allowed:
                logger.warning(
                    f"output_moderation_blocked: hash={hashlib.sha256(user_content.encode()).hexdigest()[:16]}, "
                    f"categories={mod_output.categories}, blocked_by={mod_output.blocked_by}"
                )
                # Заменяем ответ на заглушку
                full_response = "Не могу показать ответ – он мог нарушить правила"

        # ---- 10. Сохраняем ответ ассистента (с заглушкой, если модерация не прошла) ----
        if full_response:
            assistant_msg = ChatMessage(chat_id=chat_id, role="assistant", content=full_response)
            await self.repo.append_message(chat_id, assistant_msg)

        # Логируем завершение запроса
        logger.info(
            f"llm_request_completed: model={self.settings.openai.default_model}, "
            f"latency_ms={latency_ms:.2f}, "
            f"input_tokens={len(user_content.split())}, "
            f"output_tokens={len(full_response.split())}"
        )