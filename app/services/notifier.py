import httpx
from pydantic import SecretStr

from app.core.config import get_settings


async def notify_user(chat_id_tg: int, text: str) -> None:
    settings = get_settings()
    token = settings.internal_token
    header = token.get_secret_value() if isinstance(token, SecretStr) else str(token)
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{settings.bot_url}/notify",
            json={"chat_id": chat_id_tg, "text": text},
            headers={"X-Internal-Token": header},
        )
        response.raise_for_status()
