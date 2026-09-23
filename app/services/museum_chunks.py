from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

MUSEUM_DIR = Path("data/museum")

CATEGORY_BY_STEM = {
    "hours": "hours",
    "contacts": "contacts",
    "rules": "rules",
    "tickets": "tickets",
    "location": "location",
    "events": "events",
    "excursions": "excursions",
    "index": "overview",
    "natural_history": "museums",
    "hermitage_kazan": "museums",
    "cannon_yard": "museums",
    "islamic_culture": "museums",
    "annunciation_museum": "museums",
    "statehood_museum": "museums",
    "spasskaya_tower": "museums",
    "manezh": "museums",
    "prisutstvennye": "museums",
    "kul_sharif": "architecture",
    "offtopic": "other",
}

# Старый «шумный» документ — чтобы DatetimeRange за 30 дней его отсекал.
CREATED_AT_OVERRIDE = {
    "offtopic": datetime(2024, 1, 15, tzinfo=timezone.utc),
}


def chunk_text(text: str, size: int = 240, overlap: int = 40) -> list[str]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= size:
        return [cleaned]
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + size)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(cleaned):
            break
        start = max(end - overlap, start + 1)
    return chunks


def iter_museum_chunks(root: Path | None = None) -> list[dict]:
    base = root or MUSEUM_DIR
    records: list[dict] = []
    for path in sorted(base.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        category = CATEGORY_BY_STEM.get(path.stem, "other")
        created = CREATED_AT_OVERRIDE.get(
            path.stem, datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        )
        for index, chunk in enumerate(chunk_text(text)):
            source = path.name
            records.append(
                {
                    "id": str(uuid5(NAMESPACE_URL, f"{source}:{index}")),
                    "source": source,
                    "text": chunk,
                    "created_at": created,
                    "category": category,
                    "chunk_index": index,
                }
            )
    return records
