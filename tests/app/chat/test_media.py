import pytest

def test_media_module_has_functions():
    """Проверяем, что в модуле media есть все необходимые функции."""
    from app.chat import media
    assert hasattr(media, 'media_to_part')
    assert hasattr(media, 'extract_pdf_text')
    assert hasattr(media, 'extract_docx_text')
    assert hasattr(media, 'whisper_transcribe')