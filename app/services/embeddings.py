from __future__ import annotations

import hashlib
import math
from pathlib import Path

import httpx
from diskcache import Cache
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from tiktoken import encoding_for_model, get_encoding

from app.core.config import Settings, get_settings


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _encoding(model: str):
    try:
        return encoding_for_model(model.split("/")[-1])
    except KeyError:
        return get_encoding("cl100k_base")


class EmbeddingService:
    """Батчевые эмбеддинги с дисковым кешем. Повтор одного текста не ходит в API."""

    def __init__(self, settings: Settings | None = None, client: OpenAI | None = None):
        self.settings = settings or get_settings()
        self.model = self.settings.embedding_model
        self.dim = self.settings.embedding_dim
        self.batch_size = max(1, self.settings.embedding_batch_size)
        cache_dir = Path(self.settings.embedding_cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = Cache(str(cache_dir))
        self.api_calls = 0
        self._owns_http = False
        if client is not None:
            self.client = client
            self._http = None
        else:
            proxy = self.settings.http_proxy
            self._http = (
                httpx.Client(proxy=proxy, trust_env=False)
                if proxy
                else httpx.Client(trust_env=False)
            )
            self._owns_http = True
            self.client = OpenAI(
                api_key=self.settings.openai.api_key.get_secret_value(),
                base_url=self.settings.openai.base_url,
                http_client=self._http,
                timeout=self.settings.openai.request_timeout,
                max_retries=self.settings.openai.max_retries,
            )

    def close(self) -> None:
        self.cache.close()
        if self._owns_http and self._http is not None:
            self._http.close()

    def _cache_key(self, text: str) -> str:
        payload = f"{self.model}:{self.dim}:{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def count_tokens(self, texts: list[str]) -> int:
        enc = _encoding(self.model)
        return sum(len(enc.encode(t or "")) for t in texts)

    def estimate_index_cost(self, texts: list[str], usd_per_million: float = 0.02) -> dict:
        tokens = self.count_tokens(texts)
        return {
            "documents": len(texts),
            "tokens": tokens,
            "model": self.model,
            "usd_openai_list_price": round(tokens / 1_000_000 * usd_per_million, 6),
            "note": "Цена OpenAI text-embedding-3-small (~$0.02 / 1M токенов). У Polza смотрите тариф в кабинете.",
        }

    @retry(wait=wait_exponential(min=1, max=20), stop=stop_after_attempt(5))
    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        self.api_calls += 1
        payload: dict = {"model": self.model, "input": batch}
        response = self.client.embeddings.create(**payload)
        by_index = {item.index: item.embedding for item in response.data}
        return [_l2_normalize(by_index[i]) for i in range(len(batch))]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str]] = []
        for i, text in enumerate(texts):
            cached = self.cache.get(self._cache_key(text))
            if cached is not None:
                vectors[i] = list(cached)
            else:
                missing.append((i, text))
        for start in range(0, len(missing), self.batch_size):
            chunk = missing[start : start + self.batch_size]
            batch_texts = [item[1] for item in chunk]
            embedded = self._embed_batch(batch_texts)
            for (idx, raw), vector in zip(chunk, embedded):
                self.cache.set(self._cache_key(raw), vector)
                vectors[idx] = vector
        return [v or [] for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_texts(texts)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
