from unittest.mock import MagicMock

from app.services.embeddings import EmbeddingService, cosine


def _fake_response(vectors: list[list[float]]):
    data = []
    for i, vec in enumerate(vectors):
        item = MagicMock()
        item.index = i
        item.embedding = vec
        data.append(item)
    resp = MagicMock()
    resp.data = data
    return resp


def test_embed_texts_batches_and_caches(tmp_path, monkeypatch):
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "32")
    from app.core.config import get_settings

    get_settings.cache_clear()
    client = MagicMock()
    client.embeddings.create.return_value = _fake_response([[1.0, 0.0], [0.0, 1.0]])
    service = EmbeddingService(settings=get_settings(), client=client)
    texts = ["билет в кремль", "часы работы"]
    first = service.embed_texts(texts)
    second = service.embed_texts(texts)
    assert client.embeddings.create.call_count == 1
    assert first == second
    assert abs(sum(x * x for x in first[0]) - 1.0) < 1e-6
    service.close()
    get_settings.cache_clear()


def test_cosine_prefers_relevant():
    q = [1.0, 0.0]
    relevant = [0.9, 0.1]
    irrelevant = [0.0, 1.0]
    assert cosine(q, relevant) > cosine(q, irrelevant)


def test_mini_benchmark_file_shape():
    import json
    from pathlib import Path

    data = json.loads(Path("tests/eval/mini_benchmark.json").read_text(encoding="utf-8"))
    assert 5 <= len(data) <= 10
    for row in data:
        assert row["query"] and row["relevant"] and row["irrelevant"]
        assert row["relevant"] != row["irrelevant"]
