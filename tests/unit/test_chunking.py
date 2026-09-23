import json
from pathlib import Path

from app.services.chunking import get_splitter, split_russian_sentences
from app.services.retrieval_eval import evaluate_retrieval


def test_dataset_has_20_plus_questions():
    rows = json.loads(Path("tests/eval/retrieval_dataset.json").read_text(encoding="utf-8"))
    assert len(rows) >= 20
    for row in rows:
        assert row["question"]
        assert 1 <= len(row["relevant_doc_ids"]) <= 3


def test_russian_sentence_split():
    parts = split_russian_sentences("Первое предложение. Второе предложение! Третье?")
    assert len(parts) == 3


def test_splitters_build():
    assert get_splitter("fixed").chunk_size == 512
    assert get_splitter("recursive").paragraph_separator == "\n\n"


def test_metrics_hit_mrr_recall():
    retrieved = [
        ["contacts.md", "hours.md", "rules.md"],
        ["offtopic.md", "events.md"],
    ]
    gold = [["contacts.md"], ["tickets.md"]]
    metrics = evaluate_retrieval(retrieved, gold)
    assert metrics["hit_rate@5"] == 0.5
    assert metrics["mrr@10"] == 0.5
    assert metrics["recall@10"] == 0.5
