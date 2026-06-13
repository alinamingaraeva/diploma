from functools import lru_cache
from typing import List
from pathlib import Path
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Настройки для LLM-провайдера (OpenAI или совместимого, например polza.ai)."""
    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")
    
    api_key: SecretStr
    base_url: str = "https://api.openai.com/v1"          # можно переопределить в .env
    default_model: str = "gpt-4o-mini"
    request_timeout: float = 30.0
    max_retries: int = 3


class Settings(BaseSettings):
    """Главные настройки приложения, загружаемые из .env."""
    model_config = SettingsConfigDict(
        env_file=".env",                 # имя файла в корне проекта
        env_file_encoding="utf-8",       # кодировка
        env_nested_delimiter="__",       # разделитель для вложенных моделей (LLMSettings)
        extra="ignore"
    )
    
    # Вложенные настройки OpenAI/LLM (префикс OPENAI__)
    openai: LLMSettings = LLMSettings()
    
    # Redis и кеширование
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 3600
    
    # CORS
    cors_origins: List[str] = ["*"]
    
    # Логирование
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Возвращает закешированный объект настроек."""
    return Settings()