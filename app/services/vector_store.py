from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    HnswConfigDiff,
    PayloadSchemaType,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from app.core.config import Settings, get_settings


class VectorStore:
    """Обёртка над AsyncQdrantClient. URL и размерность — из настроек, не из кода."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: AsyncQdrantClient | None = None,
        collection: str | None = None,
    ):
        self.settings = settings or get_settings()
        self.collection = collection or self.settings.qdrant_collection
        self.dim = self.settings.embedding_dim
        api_key = None
        if self.settings.qdrant_api_key is not None:
            api_key = self.settings.qdrant_api_key.get_secret_value() or None
        self.client = client or AsyncQdrantClient(
            url=self.settings.qdrant_url,
            api_key=api_key,
            check_compatibility=False,
        )

    async def ensure_collection(self, distance: Distance = Distance.COSINE) -> None:
        # HNSW: явно m=16, ef_construct=100 — дефолт Qdrant, достаточно для <100k точек корпуса музея.
        existing = {c.name for c in (await self.client.get_collections()).collections}
        if self.collection in existing:
            info = await self.client.get_collection(self.collection)
            size = info.config.params.vectors.size
            if size != self.dim:
                raise ValueError(
                    f"Коллекция {self.collection} имеет размерность {size}, "
                    f"а EMBEDDING_DIM={self.dim}. Пересоздайте коллекцию."
                )
        else:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=distance),
                hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
            )
        for field_name, schema in (
            ("source", PayloadSchemaType.KEYWORD),
            ("created_at", PayloadSchemaType.DATETIME),
            ("category", PayloadSchemaType.KEYWORD),
        ):
            try:
                await self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field_name,
                    field_schema=schema,
                )
            except Exception:
                continue

    async def upsert(self, points: list[PointStruct], batch_size: int = 256) -> None:
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await self.client.upsert(
                collection_name=self.collection,
                points=batch,
                wait=(i + batch_size >= len(points)),
            )

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        query_filter: Filter | None = None,
    ) -> list[ScoredPoint]:
        result = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        return result.points
