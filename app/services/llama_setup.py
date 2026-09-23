from __future__ import annotations

import httpx
from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

from app.core.config import Settings as AppSettings


def configure_llama(settings: AppSettings, http_client: httpx.Client) -> OpenAIEmbedding:
    api_key = settings.openai.api_key.get_secret_value()
    api_base = settings.openai.base_url
    embed_model = OpenAIEmbedding(
        model_name=settings.embedding_model,
        api_key=api_key,
        api_base=api_base,
        http_client=http_client,
        embed_batch_size=settings.embedding_batch_size,
    )
    Settings.llm = OpenAI(
        model=settings.openai.default_model,
        api_key=api_key,
        api_base=api_base,
        http_client=http_client,
        timeout=settings.openai.request_timeout,
        max_retries=settings.openai.max_retries,
    )
    Settings.embed_model = embed_model
    return embed_model
