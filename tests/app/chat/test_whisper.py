import pytest

def test_whisper_transcribe_exists():
    """Проверяем, что функция whisper_transcribe определена."""
    from app.chat.media import whisper_transcribe
    assert callable(whisper_transcribe)