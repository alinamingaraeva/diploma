import json
import uuid
from typing import AsyncIterator, Optional
import httpx

class BackendClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_or_create_chat(self, owner_external_id: str, interface: str = "telegram") -> uuid.UUID:
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/chats",
                json={"owner_external_id": owner_external_id, "interface": interface}
            )
            response.raise_for_status()
            data = response.json()
            return uuid.UUID(data["chat_id"])

    async def send_message(
        self,
        chat_id: uuid.UUID,
        content: str,
        media: Optional[bytes] = None,
        mime: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Отправляет сообщение в чат. Поддерживает медиа.
        """
        data = {"content": content}
        files = None
        if media and mime:
            files = {"media": ("file", media, mime)}

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chats/{chat_id}/messages",
                data=data,
                files=files,
                headers={"Accept": "text/event-stream"}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "{\"type\": \"done\"}":
                            break
                        try:
                            payload = json.loads(data_str)
                            if payload.get("type") == "token":
                                yield payload.get("delta", "")
                            else:
                                # fallback: если нет type, может быть старый формат
                                if "delta" in payload:
                                    yield payload["delta"]
                                else:
                                    yield data_str
                        except json.JSONDecodeError:
                            # если не JSON, просто отдаём строку
                            yield data_str

    async def clear_messages(self, chat_id: uuid.UUID) -> None:
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.delete(f"{self.base_url}/chats/{chat_id}/messages")
            response.raise_for_status()