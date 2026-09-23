import json
import uuid
from collections.abc import AsyncIterator
from typing import Optional

import httpx


def friendly_http_error(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "Сервис недоступен, попробуйте позже"
    if isinstance(exc, httpx.ReadTimeout):
        return "Ответ занимает слишком долго"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return "Слишком много запросов, подождите минуту"
        if status == 403:
            return "moderation_blocked"
        if status >= 500:
            return "Внутренняя ошибка сервиса"
        return f"Ошибка сервиса ({status})"
    return str(exc)


class BackendClient:
    def __init__(
        self,
        base_url: str,
        admin_token: str = "",
        timeout: float = 30.0,
        http: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.timeout = timeout
        self._http = http
        self._owns_http = http is None

    def _client(self, read: float | None = None) -> httpx.AsyncClient:
        if self._http:
            return self._http
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3.0, read=read or 60.0, write=10.0, pool=5.0),
            trust_env=False,
        )

    async def aclose(self) -> None:
        if self._owns_http and self._http:
            await self._http.aclose()

    async def get_or_create_chat(self, owner_external_id: str, interface: str = "telegram") -> uuid.UUID:
        client = self._client()
        try:
            response = await client.post(
                f"{self.base_url}/chats",
                json={"owner_external_id": owner_external_id, "interface": interface},
            )
            response.raise_for_status()
            return uuid.UUID(response.json()["chat_id"])
        except Exception as exc:
            raise RuntimeError(friendly_http_error(exc)) from exc
        finally:
            if self._owns_http:
                await client.aclose()

    async def send_message(
        self,
        chat_id: uuid.UUID,
        content: str,
        media: Optional[bytes] = None,
        mime: Optional[str] = None,
    ) -> AsyncIterator[str]:
        data = {"content": content}
        files = {"media": ("file.bin", media, mime)} if media and mime else None
        timeout = httpx.Timeout(connect=3.0, read=120.0, write=10.0, pool=5.0)
        client = self._http or httpx.AsyncClient(timeout=timeout, trust_env=False)
        close = self._http is None
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chats/{chat_id}/messages",
                data=data,
                files=files,
                headers={"Accept": "text/event-stream"},
                timeout=timeout,
            ) as response:
                response.raise_for_status()
                event_type = "message"
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line[7:].strip() or "message"
                        continue
                    if not line.startswith("data: "):
                        continue
                    payload_raw = line[6:].strip()
                    if event_type == "sources":
                        if payload_raw:
                            yield f"[[sources:{payload_raw}]]"
                        event_type = "message"
                        continue
                    try:
                        payload = json.loads(payload_raw)
                    except json.JSONDecodeError:
                        if payload_raw and payload_raw != "[DONE]":
                            yield payload_raw
                        continue
                    event_type = "message"
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") == "token":
                        yield payload.get("delta", "")
                    elif payload.get("type") == "done":
                        message_id = payload.get("message_id")
                        if message_id:
                            yield f"[[message_id:{message_id}]]"
                        return
        except Exception as exc:
            raise RuntimeError(friendly_http_error(exc)) from exc
        finally:
            if close:
                await client.aclose()

    async def clear_messages(self, chat_id: uuid.UUID) -> None:
        client = self._client()
        try:
            response = await client.delete(f"{self.base_url}/chats/{chat_id}/messages")
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(friendly_http_error(exc)) from exc
        finally:
            if self._owns_http:
                await client.aclose()

    async def get_stats(self) -> dict:
        return await self._admin_json("GET", "/chats/admin/stats")

    async def get_users(self, limit: int = 50) -> list:
        data = await self._admin_json("GET", f"/chats/admin/users?limit={limit}")
        return data.get("users", [])

    async def broadcast(self, message: str) -> dict:
        return await self._admin_json(
            "POST",
            "/chats/admin/broadcast",
            json_body={"message": message, "interface_filter": "telegram"},
        )

    async def save_feedback(self, message_id: str, vote: str, owner_external_id: str, chat_id: str | None = None) -> None:
        client = self._client()
        try:
            response = await client.post(
                f"{self.base_url}/chats/feedback",
                json={
                    "message_id": message_id,
                    "value": vote,
                    "owner_external_id": owner_external_id,
                },
            )
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(friendly_http_error(exc)) from exc
        finally:
            if self._owns_http:
                await client.aclose()

    async def _admin_json(self, method: str, path: str, json_body: dict | None = None) -> dict:
        client = self._client()
        try:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                json=json_body,
                headers={"X-Admin-Token": self.admin_token},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise RuntimeError(friendly_http_error(exc)) from exc
        finally:
            if self._owns_http:
                await client.aclose()
