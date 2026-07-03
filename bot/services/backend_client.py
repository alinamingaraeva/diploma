import json
import uuid
from typing import AsyncIterator
import httpx

class BackendClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def get_or_create_chat(self, owner_external_id: str, interface: str = "telegram") -> uuid.UUID:
        # trust_env=False — игнорируем системный прокси
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/chats",
                json={"owner_external_id": owner_external_id, "interface": interface}
            )
            response.raise_for_status()
            data = response.json()
            return uuid.UUID(data["chat_id"])

    async def send_message(self, chat_id: uuid.UUID, content: str) -> AsyncIterator[str]:
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chats/{chat_id}/messages",
                json={"content": content},
                headers={"Accept": "text/event-stream"}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                            if "content" in payload:
                                yield payload["content"]
                            else:
                                yield data
                        except json.JSONDecodeError:
                            yield data

    async def clear_messages(self, chat_id: uuid.UUID) -> None:
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.delete(f"{self.base_url}/chats/{chat_id}/messages")
            response.raise_for_status()