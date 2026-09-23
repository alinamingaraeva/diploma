from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.services.ingestion import ingest_file

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED = {".pdf", ".docx", ".html", ".htm", ".md", ".markdown"}


def _ingest_uploaded(path: str) -> None:
    ingest_file(Path(path))


@router.post("/upload", status_code=202)
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status_code=400, detail="Поддерживаются PDF, DOCX, HTML, MD")
    dest_dir = Path("data/uploads")
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or f"upload{suffix}").name
    dest = dest_dir / f"{uuid.uuid4().hex}_{safe_name}"
    dest.write_bytes(await file.read())
    background_tasks.add_task(_ingest_uploaded, str(dest))
    return {"status": "accepted", "path": str(dest)}
