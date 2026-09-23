from functools import lru_cache
from pathlib import Path
from typing import List, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Настройки LLM-провайдера (OpenAI-совместимый API, например polza.ai)."""

    model_config = SettingsConfigDict(env_prefix="OPENAI__", extra="ignore")

    api_key: SecretStr = SecretStr("sk-placeholder")
    base_url: str = "https://api.polza.ai/v1"
    default_model: str = "openai/gpt-4o-mini"
    request_timeout: float = 30.0
    max_retries: int = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "museum-consultant"
    debug: bool = False
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:8000"])
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    openai: LLMSettings = Field(default_factory=LLMSettings)
    log_level: str = "INFO"
    http_proxy: str | None = None
    security_filters_enabled: bool = True

    chat_repository: Literal["json", "postgres"] = "json"
    chat_storage_dir: Path = Path("./var/chats")
    chat_context_strategy: Literal["sliding", "hybrid"] = "sliding"
    chat_context_window: int = 10
    model_context_window: int = 128000
    response_tokens: int = 4096
    safety_margin_tokens: int = 256
    database_url: str = "postgresql+asyncpg://chat_user:chat_pass@localhost:5432/chat_db"

    bot_url: str = "http://localhost:9000"
    internal_token: SecretStr = SecretStr("change-me-internal")
    admin_token: SecretStr = SecretStr("change-me-admin")

    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 1536
    embedding_batch_size: int = 32
    embedding_cache_dir: Path = Path("./var/embeddings_cache")

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "documents"

    rag_data_dir: Path = Path("./data/kb")
    rag_chunk_size: int = 1024
    rag_chunk_overlap: int = 64
    rag_similarity_top_k: int = 5
    rag_chunk_strategy: Literal["fixed", "recursive", "semantic"] = "fixed"
    rag_retrieve_k: int = 24
    rag_rerank_enabled: bool = False
    rag_rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rag_collection: str = "rag_eval_1024"
    rag_baremetal_collection: str = "rag_block_03_bare"
    rag_score_threshold: float = 0.38
    rag_docstore_path: Path = Path("./var/ingestion/docstore_1024.json")
    official_site_enabled: bool = True
    official_site_base_url: str = "https://kazan-kremlin.ru"
    official_site_cache_ttl_seconds: int = 600
    official_site_timeout_seconds: float = 12.0

    eval_judge_model: str = "openai/gpt-4o-mini"
    eval_embed_model: str = "openai/text-embedding-3-small"
    eval_concurrency: int = 2
    phoenix_enabled: bool = True

    agent_checkpointer: Literal["memory", "sqlite", "postgres"] = "sqlite"
    agent_sqlite_path: Path = Path("./var/agent_checkpoints.sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
