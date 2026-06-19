from app.observability.pii import redact_pii

def test_redact_email_and_phone():
    text = "Мой email ivan@mail.ru, тел +7 (999) 123-45-67, карта 4111 1111 1111 1111"
    redacted = redact_pii(text)
    assert "[EMAIL]" in redacted
    assert "ivan@mail.ru" not in redacted
    assert "[PHONE_RU]" in redacted
    assert "+7 (999) 123-45-67" not in redacted
    assert "[CARD]" in redacted
    assert "4111 1111 1111 1111" not in redacted

def test_redact_inn_passport():
    text = "ИНН 1234567890, паспорт 45 12 345678"
    redacted = redact_pii(text)
    assert "[INN]" in redacted
    assert "1234567890" not in redacted
    assert "[PASSPORT]" in redacted
    assert "45 12 345678" not in redacted