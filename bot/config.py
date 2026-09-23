from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    backend_url: str = "http://localhost:8000"
    bot_admin_ids: List[int] = []
    backend_timeout: float = 30.0
    proxy: Optional[str] = None
    bot_api_port: int = 9000
    internal_token: str = "change-me-internal"
    admin_token: str = "change-me-admin"


def get_bot_settings() -> BotSettings:
    return BotSettings()
