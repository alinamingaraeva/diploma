from pathlib import Path
from types import SimpleNamespace

from app.services.rag_common import FALLBACK_ANSWER, pack_result, source_item
from app.services.rag import RAGService


def test_rag_corpus_has_ten_docs_and_offtopic():
    root = Path("data/rag-block-03")
    files = sorted(p.name for p in root.glob("*.md"))
    assert len(files) == 10
    assert "offtopic.md" in files
    assert "contacts.md" in files
    assert "hours.md" in files


def test_pack_result_fallback_by_threshold():
    sources = [
        source_item("шум", "offtopic.md", 0.21),
        source_item("ещё шум", "events.md", 0.19),
        source_item("и ещё", "rules.md", 0.11),
    ]
    packed = pack_result("выдуманный ответ", sources, threshold=0.38)
    assert packed["answer"] == FALLBACK_ANSWER
    assert packed["top_score"] == 0.21
    assert len(packed["sources"]) == 3


def test_pack_result_keeps_answer_when_relevant():
    sources = [source_item("визит-центр", "contacts.md", 0.61)]
    packed = pack_result("Звоните в визит-центр.", sources, threshold=0.38)
    assert "визит-центр" in packed["answer"]
    assert packed["top_score"] == 0.61


def _node(file_name: str, score: float = 0.5):
    inner = SimpleNamespace(metadata={"file_name": file_name})
    return SimpleNamespace(node=inner, score=score)


def test_unique_by_file_keeps_one_stem():
    rag = RAGService.__new__(RAGService)
    nodes = [
        _node("contacts.md"),
        _node("contacts.html"),
        _node("contacts.pdf"),
        _node("tickets.md"),
        _node("rules.md"),
    ]
    unique = rag._unique_by_file(nodes, top_n=5)
    stems = [n.node.metadata["file_name"] for n in unique]
    assert stems == ["contacts.md", "tickets.md", "rules.md"]


def test_unique_by_file_strips_pdf_hash_prefix():
    rag = RAGService.__new__(RAGService)
    nodes = [
        _node("hours.md"),
        _node("f5f0b047990c41008f6bc7299e8c99b9_hours.pdf"),
        _node("tickets.md"),
    ]
    unique = rag._unique_by_file(nodes, top_n=5)
    stems = [n.node.metadata["file_name"] for n in unique]
    assert stems == ["hours.md", "tickets.md"]
