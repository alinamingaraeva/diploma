"""Индексация корпуса. Повторный запуск не дублирует чанки (DocstoreStrategy.UPSERTS)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.services.ingestion import load_documents, run_ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def resolve_roots(raw: Path) -> list[Path]:
    if raw.name == "data":
        return [p for p in (raw / "kb", raw / "uploads") if p.exists()]
    return [raw]


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    settings = get_settings()
    documents = []
    failed = []
    for root in resolve_roots(target):
        docs, bad = load_documents(root)
        documents.extend(docs)
        failed.extend(bad)
    if len(documents) < 1:
        raise SystemExit(f"Нет документов в {target}. Сначала: python scripts/download_data.py")
    stats = run_ingest(documents, settings=settings, show_progress=True)
    print(f"{stats['changed']} changed, {stats['unchanged']} unchanged")
    print(f"documents={stats['documents']} nodes_emitted={stats['nodes_emitted']} failed={len(failed)}")
    for path in failed:
        print(f"failed {path}")


if __name__ == "__main__":
    main()
