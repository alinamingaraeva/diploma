"""Загрузка корпуса музея в Qdrant. Повторный запуск не плодит дубли (uuid5)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from qdrant_client.models import DatetimeRange, Distance, FieldCondition, Filter, MatchValue, PointStruct
from tqdm import tqdm

from app.core.config import get_settings
from app.services.embeddings import EmbeddingService
from app.services.museum_chunks import iter_museum_chunks
from app.services.vector_store import VectorStore

QUERIES = [
    "Телефон визит-центра Казанского Кремля",
    "Часы работы музея естественной истории в пятницу",
    "Где купить билет в Эрмитаж-Казань",
    "Можно ли зайти в Кремль с собакой",
    "Экскурсия в мечеть Кул-Шариф в пятницу",
]


def to_points(records: list[dict], vectors: list[list[float]]) -> list[PointStruct]:
    points = []
    for row, vector in zip(records, vectors):
        if len(vector) != get_settings().embedding_dim:
            raise ValueError(f"Вектор длины {len(vector)}, ожидается EMBEDDING_DIM")
        points.append(
            PointStruct(
                id=row["id"],
                vector=vector,
                payload={
                    "source": row["source"],
                    "text": row["text"],
                    "created_at": row["created_at"].isoformat(),
                    "category": row["category"],
                    "chunk_index": row["chunk_index"],
                },
            )
        )
    return points


async def load_collection(name: str, distance: Distance, points: list[PointStruct]) -> VectorStore:
    store = VectorStore(collection=name)
    store.collection = name
    await store.ensure_collection(distance=distance)
    await store.upsert(points, batch_size=128)
    return store


def _hit_row(hit) -> dict:
    payload = hit.payload or {}
    text = str(payload.get("text") or "").replace("\n", " ")
    return {
        "id": str(hit.id),
        "source": payload.get("source"),
        "category": payload.get("category"),
        "score": round(float(hit.score), 4),
        "text": text[:120],
    }


async def compare_metrics(points: list[PointStruct], embedder: EmbeddingService) -> list[dict]:
    cosine_store = await load_collection("documents_cosine", Distance.COSINE, points)
    dot_store = await load_collection("documents_dot", Distance.DOT, points)
    rows = []
    for query in QUERIES:
        vector = embedder.embed_query(query)
        cos_hits = await cosine_store.search(vector, top_k=5)
        dot_hits = await dot_store.search(vector, top_k=5)
        cos_ids = [str(p.id) for p in cos_hits]
        dot_ids = [str(p.id) for p in dot_hits]
        rows.append(
            {
                "query": query,
                "cosine": cos_ids,
                "dot": dot_ids,
                "same": cos_ids == dot_ids,
            }
        )
    await cosine_store.client.delete_collection("documents_cosine")
    await dot_store.client.delete_collection("documents_dot")
    await cosine_store.client.close()
    await dot_store.client.close()
    return rows


async def demo_filters(store: VectorStore, embedder: EmbeddingService) -> dict:
    hours_vector = embedder.embed_query("часы работы музеев")
    match_filter = Filter(must=[FieldCondition(key="category", match=MatchValue(value="hours"))])
    match_hits = await store.search(hours_vector, top_k=3, query_filter=match_filter)

    chakchak_vector = embedder.embed_query("рецепт чак-чака и погода в Сочи")
    since = datetime.now(timezone.utc) - timedelta(days=30)
    range_filter = Filter(must=[FieldCondition(key="created_at", range=DatetimeRange(gte=since))])
    unfiltered = await store.search(chakchak_vector, top_k=3)
    range_hits = await store.search(chakchak_vector, top_k=3, query_filter=range_filter)

    museums_vector = embedder.embed_query("экспозиция музея естественной истории")
    composite_filter = Filter(
        must=[FieldCondition(key="category", match=MatchValue(value="museums"))],
        must_not=[FieldCondition(key="source", match=MatchValue(value="offtopic.md"))],
    )
    composite_hits = await store.search(museums_vector, top_k=3, query_filter=composite_filter)
    return {
        "match_category_hours": [_hit_row(h) for h in match_hits],
        "range_unfiltered_chakchak": [_hit_row(h) for h in unfiltered],
        "range_created_30d": [_hit_row(h) for h in range_hits],
        "must_museums_not_offtopic": [_hit_row(h) for h in composite_hits],
    }


async def async_main(compare: bool) -> None:
    records = iter_museum_chunks()
    print(f"chunks: {len(records)}")
    if len(records) < 100:
        raise SystemExit("Нужно 100+ чанков — уменьшите размер окна в museum_chunks.py")
    embedder = EmbeddingService()
    texts = [row["text"] for row in records]
    vectors: list[list[float]] = []
    batch = 32
    for i in tqdm(range(0, len(texts), batch), desc="embeddings"):
        vectors.extend(embedder.embed_texts(texts[i : i + batch]))
    points = to_points(records, vectors)
    store = VectorStore()
    await store.ensure_collection()
    await store.upsert(points, batch_size=128)
    info = await store.client.get_collection(store.collection)
    print(f"points_count={info.points_count} dim={info.config.params.vectors.size}")
    if compare:
        rows = await compare_metrics(points, embedder)
        print("cosine_vs_dot:")
        for row in rows:
            print(row)
        print("filters:", await demo_filters(store, embedder))
    embedder.close()
    await store.client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true", help="cosine vs dot + примеры фильтров")
    args = parser.parse_args()
    asyncio.run(async_main(args.compare))


if __name__ == "__main__":
    main()
