import pytest
from bot.services.backend_client import BackendClient
import inspect

def test_backend_client_send_message_signature():
    """Проверяем, что метод send_message принимает media и mime."""
    client = BackendClient(base_url="http://test")
    sig = inspect.signature(client.send_message)
    assert "media" in sig.parameters
    assert "mime" in sig.parameters
    assert "content" in sig.parameters

def test_backend_client_has_get_or_create_chat():
    client = BackendClient(base_url="http://test")
    assert hasattr(client, 'get_or_create_chat')
    assert hasattr(client, 'clear_messages')