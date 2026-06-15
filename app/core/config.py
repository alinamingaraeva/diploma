from functools import lru_cache
from typing import List
from pathlib import Path
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Настройки для LLM-провайдера (OpenAI или совместимого, например polza.ai)."""
    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")
    
    api_key: SecretStr
    base_url: str = "https://api.polza.ai/v1"          # можно переопределить в .env
    default_model: str = "openai/gpt-4o-mini"
    request_timeout: float = 30.0
    max_retries: int = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "llm-service-asdf"
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    openai: LLMSettings = Field(default_factory=LLMSettings)
    
    # CORS
    cors_origins: List[str] = ["*"]
    
    # Логирование
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Возвращает закешированный объект настроек."""
    return Settings()