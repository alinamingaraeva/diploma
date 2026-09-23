"""Тот же RAG без LlamaIndex: файлы → чанки → эмбеддинги → query_points → LLM."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import Settings, get_settings
from app.services.embeddings import EmbeddingService
from app.services.museum_chunks import chunk_text
from app.services.rag_common import (
    QA_RULES,
    make_sync_http_client,
    pack_result,
    qdrant_api_key,
    source_item,
)


class BaremetalRAGService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._http = make_sync_http_client(self.settings)
        self.embedder = EmbeddingService(self.settings)
        self.llm = OpenAI(
            api_key=self.settings.openai.api_key.get_secret_value(),
            base_url=self.settings.openai.base_url,
            http_client=self._http,
            timeout=self.settings.openai.request_timeout,
            max_retries=self.settings.openai.max_retries,
        )
        self.client = QdrantClient(
            url=self.settings.qdrant_url,
            api_key=qdrant_api_key(self.settings),
            check_compatibility=False,
        )
        self._ready = False

    def _load_chunks(self) -> list[dict]:
        root = Path(self.settings.rag_data_dir)
        records: list[dict] = []
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            pieces = chunk_text(
                text,
                size=self.settings.rag_chunk_size,
                overlap=self.settings.rag_chunk_overlap,
            )
            created = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            for index, piece in enumerate(pieces):
                records.append(
                    {
                        "id": str(uuid5(NAMESPACE_URL, f"bare:{path.name}:{index}")),
                        "source": path.name,
                        "text": piece,
                        "created_at": created.isoformat(),
                    }
                )
        return records

    def _ensure_collection(self) -> None:
        name = self.settings.rag_baremetal_collection
        existing = {item.name for item in self.client.get_collections().collections}
        if name in existing:
            size = self.client.get_collection(name).config.params.vectors.size
            if size != self.settings.embedding_dim:
                raise ValueError(
                    f"Коллекция {name} имеет размерность {size}, "
                    f"а EMBEDDING_DIM={self.settings.embedding_dim}"
                )
            return
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=self.settings.embedding_dim, distance=Distance.COSINE),
        )

    def build(self) -> None:
        self._ensure_collection()
        name = self.settings.rag_baremetal_collection
        info = self.client.get_collection(name)
        if (info.points_count or 0) > 0:
            self._ready = True
            return
        records = self._load_chunks()
        if len(records) < 10:
            raise RuntimeError("Корпус rag-block-03 слишком мал для индексации")
        vectors = self.embedder.embed_documents([row["text"] for row in records])
        points = [
            PointStruct(
                id=row["id"],
                vector=vector,
                payload={
                    "source": row["source"],
                    "text": row["text"],
                    "created_at": row["created_at"],
                },
            )
            for row, vector in zip(records, vectors)
        ]
        batch = 128
        for i in range(0, len(points), batch):
            chunk = points[i : i + batch]
            self.client.upsert(
                collection_name=name,
                points=chunk,
                wait=(i + batch >= len(points)),
            )
        self._ready = True

    def answer(self, question: str) -> dict:
        if not self._ready:
            self.build()
        query_vector = self.embedder.embed_query(question)
        result = self.client.query_points(
            collection_name=self.settings.rag_baremetal_collection,
            query=query_vector,
            limit=self.settings.rag_similarity_top_k,
            with_payload=True,
        )
        sources = []
        context_parts = []
        for point in result.points:
            payload = point.payload or {}
            text = str(payload.get("text") or "")
            sources.append(source_item(text, payload.get("source"), point.score))
            context_parts.append(f"[{payload.get('source')}]\n{text}")
        context = "\n\n".join(context_parts) if context_parts else "(пусто)"
        completion = self.llm.chat.completions.create(
            model=self.settings.openai.default_model,
            messages=[
                {"role": "system", "content": QA_RULES},
                {
                    "role": "user",
                    "content": f"Контекст:\n{context}\n\nВопрос: {question}",
                },
            ],
        )
        answer = completion.choices[0].message.content or ""
        packed = pack_result(answer, sources, self.settings.rag_score_threshold)
        return packed

    def close(self) -> None:
        self.embedder.close()
        self.client.close()
        self._http.close()


def main() -> None:
    service = BaremetalRAGService()
    try:
        service.build()
        result = service.answer("Какой телефон визит-центра Казанского Кремля?")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
