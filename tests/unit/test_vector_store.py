from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.museum_chunks import chunk_text, iter_museum_chunks
from app.services.vector_store import VectorStore


def test_corpus_has_100_plus_chunks():
    records = iter_museum_chunks()
    assert len(records) >= 100
    assert len({row["id"] for row in records}) == len(records)
    assert any(row["category"] == "museums" for row in records)
    assert any(row["category"] == "hours" for row in records)
    offtopic = [row for row in records if row["source"] == "offtopic.md"]
    assert offtopic
    assert offtopic[0]["created_at"].year == 2024


def test_chunk_text_overlap():
    text = "слово " * 80
    chunks = chunk_text(text, size=40, overlap=10)
    assert len(chunks) >= 3


@pytest.mark.asyncio
async def test_vector_store_ensure_and_search():
    client = AsyncMock()
    collections = MagicMock()
    collections.collections = []
    client.get_collections.return_value = collections
    result = MagicMock()
    result.points = []
    client.query_points.return_value = result
    store = VectorStore(client=client, collection="documents")
    store.dim = 1536
    await store.ensure_collection()
    client.create_collection.assert_awaited()
    hits = await store.search([0.0] * 8, top_k=3)
    assert hits == []
