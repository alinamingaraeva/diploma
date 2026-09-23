from pathlib import Path

from llama_index.core import Document

from app.services.ingestion import enrich_document
from app.services.rag import REFUSAL
from app.services.rag_common import FALLBACK_ANSWER, pack_result, source_item


def test_enrich_sets_category_source_and_excludes_noise(tmp_path: Path):
    root = tmp_path / "kb"
    path = root / "hours" / "hours.md"
    path.parent.mkdir(parents=True)
    path.write_text("часы работы", encoding="utf-8")
    doc = Document(text="часы работы")
    out = enrich_document(doc, path, root)
    assert out.metadata["source"] == "hours.md"
    assert out.metadata["file_name"] == "hours.md"
    assert out.metadata["category"] == "hours"
    assert "created_at" in out.metadata
    assert "created_at" in out.excluded_embed_metadata_keys
    assert "file_path" in out.excluded_embed_metadata_keys
    assert out.doc_id


def test_enrich_reads_version_and_author(tmp_path: Path):
    root = tmp_path / "kb"
    path = root / "rules" / "rules_v2.docx"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"pk")
    doc = Document(text="правила", metadata={"author": "Музей"})
    out = enrich_document(doc, path, root)
    assert out.metadata["version"] == "2"
    assert out.metadata["author"] == "Музей"


def test_score_guard_skips_generation_below_threshold():
    sources = [
        source_item("шум", "offtopic.md", 0.21),
        source_item("ещё", "events.md", 0.11),
    ]
    packed = pack_result("выдуманный ответ", sources, threshold=0.38)
    assert packed["answer"] == FALLBACK_ANSWER
    assert packed["answer"] == REFUSAL
    assert packed["top_score"] == 0.21
