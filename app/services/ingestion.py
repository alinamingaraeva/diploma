"""Загрузка файлов и metadata-обогащение для IngestionPipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from llama_index.core import Document, SimpleDirectoryReader
from llama_index.core.ingestion import DocstoreStrategy, IngestionPipeline
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core.vector_stores.types import BasePydanticVectorStore
from llama_index.readers.file import DocxReader, HTMLTagReader, MarkdownReader, PyMuPDFReader
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import Settings, get_settings
from app.services.chunking import get_splitter
from app.services.llama_setup import configure_llama
from app.services.rag_common import make_sync_http_client, qdrant_api_key

logger = logging.getLogger(__name__)

READERS = {
    ".md": MarkdownReader(),
    ".markdown": MarkdownReader(),
    ".html": HTMLTagReader(tag="body"),
    ".htm": HTMLTagReader(tag="body"),
    ".pdf": PyMuPDFReader(),
    ".docx": DocxReader(),
}


def _version_from_name(stem: str) -> str | None:
    parts = stem.split("_v")
    if len(parts) == 2 and parts[1].replace(".", "").isdigit():
        return parts[1]
    return None


def _page_from_metadata(metadata: dict, fallback: int | str = 0) -> int | str:
    page = metadata.get("page", metadata.get("page_label"))
    if page is not None:
        return page
    source = metadata.get("source")
    if source is not None and str(source).isdigit():
        return int(source)
    return fallback


def _as_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _docx_author(path: Path) -> str | None:
    if path.suffix.lower() != ".docx":
        return None
    try:
        from docx import Document as DocxDocument

        return DocxDocument(str(path)).core_properties.author or None
    except Exception:
        return None


def enrich_document(document: Document, path: Path, root: Path) -> Document:
    try:
        rel = path.resolve().relative_to(root.resolve())
        category = rel.parts[0] if len(rel.parts) > 1 else (root.name or "general")
    except ValueError:
        category = path.parent.name or "general"
    page = _page_from_metadata(document.metadata or {}, 0)
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    document.metadata["source"] = path.name
    document.metadata["file_name"] = path.name
    document.metadata["created_at"] = modified
    document.metadata["last_modified"] = modified
    document.metadata["category"] = category
    document.metadata["page"] = page
    version = _version_from_name(path.stem)
    if version:
        document.metadata["version"] = version
    author = document.metadata.get("author") or _docx_author(path)
    if author:
        document.metadata["author"] = str(author)
    else:
        document.metadata.pop("author", None)
    document.excluded_embed_metadata_keys = [
        "created_at",
        "last_modified",
        "version",
        "file_path",
        "file_size",
        "creation_date",
        "last_modified_date",
    ]
    text = _as_text(getattr(document, "text", "") or document.get_content())
    document.set_content(text)
    document.doc_id = str(uuid5(NAMESPACE_URL, f"{path.resolve()}:{page}"))
    document.id_ = document.doc_id
    return document


def load_file(path: Path, root: Path) -> list[Document]:
    reader = SimpleDirectoryReader(
        input_files=[str(path)],
        filename_as_id=False,
        file_extractor={path.suffix.lower(): READERS[path.suffix.lower()]},
    )
    loaded = reader.load_data()
    if not loaded:
        raise ValueError(f"ридер не извлёк текст из {path}")
    documents = []
    for index, item in enumerate(loaded):
        page = _page_from_metadata(item.metadata or {}, index)
        item.doc_id = str(uuid5(NAMESPACE_URL, f"{path.resolve()}:{page}"))
        item.id_ = item.doc_id
        documents.append(enrich_document(item, path, root))
    return documents


def load_documents(root: Path) -> tuple[list[Document], list[Path]]:
    failed: list[Path] = []
    documents: list[Document] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in READERS:
            continue
        if path.name.endswith(".failed"):
            continue
        try:
            documents.extend(load_file(path, root))
        except Exception as exc:
            logger.exception("ingest_failed path=%s error=%s", path, exc)
            failed_path = path.with_name(path.name + ".failed")
            try:
                path.rename(failed_path)
            except OSError:
                logger.error("cannot_rename_failed path=%s", path)
            failed.append(failed_path)
    return documents, failed


def build_pipeline(settings: Settings | None = None) -> tuple[IngestionPipeline, SimpleDocumentStore, Path]:
    settings = settings or get_settings()
    http = make_sync_http_client(settings)
    embed_model = configure_llama(settings, http)
    splitter = get_splitter(
        settings.rag_chunk_strategy,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        embed_model=embed_model,
    )
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=qdrant_api_key(settings),
        check_compatibility=False,
    )
    vector_store: BasePydanticVectorStore = QdrantVectorStore(
        client=client,
        collection_name=settings.rag_collection,
    )
    store_path = Path(settings.rag_docstore_path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    if store_path.exists():
        docstore = SimpleDocumentStore.from_persist_path(str(store_path))
    else:
        docstore = SimpleDocumentStore()
    pipeline = IngestionPipeline(
        transformations=[splitter, embed_model],
        vector_store=vector_store,
        docstore=docstore,
        docstore_strategy=DocstoreStrategy.UPSERTS,
    )
    pipeline._http_client = http  # type: ignore[attr-defined]
    return pipeline, docstore, store_path


def persist_docstore(docstore: SimpleDocumentStore, store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    docstore.persist(persist_path=str(store_path))


def _hash_stats(before: dict, after: dict) -> tuple[int, int]:
    changed = sum(1 for key, value in after.items() if before.get(key) != value)
    unchanged = max(len(after) - changed, 0)
    return changed, unchanged


def run_ingest(documents: list[Document], settings: Settings | None = None, show_progress: bool = False) -> dict:
    settings = settings or get_settings()
    pipeline, docstore, store_path = build_pipeline(settings)
    try:
        before = dict(docstore.get_all_document_hashes() or {})
        nodes = pipeline.run(documents=documents, show_progress=show_progress)
        persist_docstore(docstore, store_path)
        after = dict(docstore.get_all_document_hashes() or {})
        changed, unchanged = _hash_stats(before, after)
        return {
            "changed": changed,
            "unchanged": unchanged,
            "nodes_emitted": len(nodes or []),
            "documents": len(documents),
        }
    finally:
        vector_store = pipeline.vector_store
        client = getattr(vector_store, "client", None)
        if client is not None:
            client.close()
        http = getattr(pipeline, "_http_client", None)
        if http is not None:
            http.close()


def ingest_file(path: Path, settings: Settings | None = None) -> dict:
    root = path.parent
    documents = load_file(path, root)
    return run_ingest(documents, settings=settings)
