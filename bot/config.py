from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    backend_url: str = "http://localhost:8000"
    bot_admin_ids: List[int] = []
    backend_timeout: float = 30.0
    proxy: str | None = None

def get_bot_settings() -> BotSettings:
    return BotSettings()