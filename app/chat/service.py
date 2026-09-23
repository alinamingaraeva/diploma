import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile
from structlog import get_logger

from app.chat.context import build_context, fit_to_budget
from app.chat.domain import Chat, ChatMessage
from app.chat.media import media_to_part, set_openai_client
from app.chat.repository import ChatRepository
from app.llm.client import ToolCallingClient
from app.moderation.service import ModerationService
from app.observability.pii import prompt_hash, redact_pii
from app.prompts.loader import render_system_prompt
from app.services.security.input_validator import validate_input
from app.services.security.output_filter import filter_output

logger = get_logger(__name__)


class ChatService:
    def __init__(self, repository: ChatRepository, llm_client, settings, canary: str = "", rag_service=None):
        self.repo = repository
        self.llm = llm_client
        self.settings = settings
        self.canary = canary
        self.rag = rag_service
        self.moderation = ModerationService(openai_client=self.llm.openai)
        self.tools = ToolCallingClient(self.llm.openai, settings.openai.default_model)
        set_openai_client(llm_client.openai)

    async def create_chat(
        self,
        owner_external_id: str,
        interface: str,
        system_prompt: Optional[str] = None,
    ) -> Chat:
        prompt = system_prompt or render_system_prompt(canary=self.canary)
        return await self.repo.get_or_create_chat(owner_external_id, interface, prompt)

    async def get_chat(self, chat_id: UUID) -> Chat | None:
        return await self.repo.get_chat(chat_id)

    async def get_history(self, chat_id: UUID, limit: int = 50) -> list[ChatMessage]:
        return await self.repo.list_messages(chat_id, limit=limit)

    async def clear_history(self, chat_id: UUID) -> None:
        await self.repo.soft_delete_messages(chat_id)

    async def send_message(
        self,
        chat_id: UUID,
        user_content: str,
        media: Optional[UploadFile] = None,
    ) -> AsyncIterator[str]:
        validation = validate_input(user_content)
        if not validation.ok:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "input_rejected", "message": validation.reason}},
            )

        mod_result = await self.moderation.check_input(user_content)
        if not mod_result.allowed:
            logger.warning(
                "input_moderation_blocked",
                hash=hashlib.sha256(user_content.encode()).hexdigest()[:16],
                preview=redact_pii(user_content)[:120],
                categories=mod_result.categories,
                blocked_by=mod_result.blocked_by,
            )
            raise HTTPException(
                status_code=403,
                detail={"code": "moderation_blocked", "categories": mod_result.categories},
            )

        media_part = None
        if media:
            media_part = await media_to_part(media)

        user_msg = ChatMessage(
            chat_id=chat_id,
            role="user",
            content=user_content,
            media_refs=(
                {
                    "mime": media.content_type,
                    "size": getattr(media, "size", None),
                    "filename": media.filename,
                    "part": media_part,
                }
                if media_part
                else None
            ),
        )
        await self.repo.append_message(chat_id, user_msg)

        chat = await self.repo.get_chat(chat_id)
        if not chat:
            raise ValueError("Chat not found")
        history = await self.repo.list_messages(chat_id, limit=100)
        if not chat.system_prompt:
            chat.system_prompt = render_system_prompt(canary=self.canary)

        messages = build_context(
            chat,
            history,
            strategy=self.settings.chat_context_strategy,
            window=self.settings.chat_context_window,
        )
        budget = (
            self.settings.model_context_window
            - self.settings.response_tokens
            - self.settings.safety_margin_tokens
        )
        messages = fit_to_budget(messages, budget)

        start_time = time.perf_counter()
        full_response = ""
        assistant_id = None
        rag_sources = None

        try:
            if media_part:
                async for delta in self._stream_completion(messages):
                    full_response += delta
                    yield delta
            elif self.rag is not None:
                prior = [
                    {"role": item.role, "content": item.content or ""}
                    for item in history
                    if item.role in {"user", "assistant"}
                ]
                if prior and prior[-1]["role"] == "user" and prior[-1]["content"] == user_content:
                    prior = prior[:-1]
                rag_result = await asyncio.to_thread(self.rag.answer, user_content, prior)
                full_response = rag_result.get("answer") or ""
                rag_sources = rag_result.get("sources") or []
                for i in range(0, len(full_response), 24):
                    yield full_response[i : i + 24]
            else:
                history_for_tools = [m for m in messages if m.get("role") != "system"][:-1]
                result = await self.tools.complete(
                    user_input=user_content,
                    history=history_for_tools,
                    canary=self.canary,
                )
                full_response = result["text"]
                for i in range(0, len(full_response), 24):
                    yield full_response[i : i + 24]
        except Exception as exc:
            logger.error("stream_error", error=str(exc))
            if full_response:
                logger.warning("stream_interrupted", accumulated=len(full_response))
            raise

        latency_ms = (time.perf_counter() - start_time) * 1000

        if full_response:
            try:
                full_response = filter_output(
                    full_response,
                    system_prompt=chat.system_prompt or "",
                    canary=f"CANARY_{self.canary}" if self.canary else "",
                )
            except ValueError:
                full_response = "Не могу показать ответ – он мог нарушить правила"

            mod_output = await self.moderation.check_output(full_response)
            if not mod_output.allowed:
                logger.warning(
                    "output_moderation_blocked",
                    hash=prompt_hash(user_content),
                    categories=mod_output.categories,
                    blocked_by=mod_output.blocked_by,
                )
                full_response = "Не могу показать ответ – он мог нарушить правила"

            assistant_msg = ChatMessage(
                chat_id=chat_id,
                role="assistant",
                content=full_response,
                media_refs={"sources": rag_sources} if rag_sources else None,
            )
            await self.repo.append_message(chat_id, assistant_msg)
            assistant_id = assistant_msg.id
            if rag_sources:
                yield f"[[sources:{json.dumps(rag_sources, ensure_ascii=False)}]]"

        logger.info(
            "llm_request_completed",
            model=self.settings.openai.default_model,
            latency_ms=round(latency_ms, 2),
            prompt_hash=prompt_hash(user_content),
            prompt_preview=redact_pii(user_content)[:120],
            output_preview=redact_pii(full_response)[:120],
            message_id=str(assistant_id) if assistant_id else None,
        )
        if assistant_id:
            yield f"\n[[message_id:{assistant_id}]]"

    async def _stream_completion(self, messages: list[dict]) -> AsyncIterator[str]:
        stream = await self.llm.openai.chat.completions.create(
            model=self.settings.openai.default_model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
