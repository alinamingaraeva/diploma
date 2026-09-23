import base64
from io import BytesIO
from typing import Dict, Any
from fastapi import UploadFile
from openai import AsyncOpenAI
import pypdf
from docx import Document

# Инициализация OpenAI клиента (будет передан извне или создан внутри)
_openai_client = None

def set_openai_client(client: AsyncOpenAI):
    global _openai_client
    _openai_client = client

def get_openai_client() -> AsyncOpenAI:
    if _openai_client is None:
        raise RuntimeError("OpenAI client not set")
    return _openai_client

async def media_to_part(media: UploadFile) -> Dict[str, Any]:
    """
    Преобразует загруженный медиафайл в content-part для OpenAI Chat Completions API.
    """
    mime = media.content_type or ""
    filename = media.filename or "file"
    if not mime or mime == "application/octet-stream":
        lower = filename.lower()
        if lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            mime = "image/jpeg" if lower.endswith((".jpg", ".jpeg")) else f"image/{lower.rsplit('.', 1)[-1]}"
        elif lower.endswith(".ogg"):
            mime = "audio/ogg"
        elif lower.endswith(".pdf"):
            mime = "application/pdf"
        elif lower.endswith(".docx"):
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    data = await media.read()

    if mime.startswith("image/"):
        b64 = base64.b64encode(data).decode()
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"}
        }

    if mime.startswith("audio/") or mime == "application/ogg":
        transcript = await whisper_transcribe(data, filename)
        return {
            "type": "text",
            "text": f"[пользователь сказал голосом]:\n{transcript}"
        }

    if mime == "application/pdf":
        text = extract_pdf_text(data)[:30000]
        return {
            "type": "text",
            "text": f"[документ PDF]:\n{text}"
        }

    if mime.endswith("wordprocessingml.document"):
        text = extract_docx_text(data)[:30000]
        return {
            "type": "text",
            "text": f"[документ DOCX]:\n{text}"
        }

    raise ValueError(f"Unsupported media type: {mime}")

async def whisper_transcribe(audio_bytes: bytes, filename: str) -> str:
    """
    Отправляет аудио в Whisper-1 и возвращает текст.
    Поддерживает ogg, m4a, mp3, wav, flac, webm.
    """
    client = get_openai_client()
    f = BytesIO(audio_bytes)
    f.name = filename  # важно для определения формата
    try:
        result = await client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )
        return result.text
    except Exception as e:
        raise RuntimeError(f"Whisper transcription failed: {e}")

def extract_pdf_text(data: bytes) -> str:
    """Извлекает текст из PDF с помощью pypdf."""
    try:
        reader = pypdf.PdfReader(BytesIO(data))
        text = ""
        for i, page in enumerate(reader.pages):
            if i >= 50:  # ограничим количество страниц
                break
            page_text = page.extract_text() or ""
            text += page_text + "\n"
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}")

def extract_docx_text(data: bytes) -> str:
    """Извлекает текст из DOCX с помощью python-docx."""
    try:
        doc = Document(BytesIO(data))
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += cell.text + " "
                text += "\n"
        return text.strip()
    except Exception as e:
        raise RuntimeError(f"DOCX extraction failed: {e}")