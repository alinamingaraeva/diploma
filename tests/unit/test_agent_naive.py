from app.services.agent_naive import DISPATCH, get_current_time, send_telegram_message


def test_dispatch_allowlist_has_three_tools():
    assert set(DISPATCH) == {
        "search_knowledge_base",
        "get_current_time",
        "send_telegram_message",
    }
    assert DISPATCH.get("get_user_balance") is None


def test_get_current_time_uses_zoneinfo():
    stamp = get_current_time("Europe/Moscow")
    assert "T" in stamp
    assert get_current_time("Not/AZone").startswith("ошибка timezone")


def test_telegram_stub_does_not_need_network(capsys):
    text = send_telegram_message("12345", "тест")
    assert "12345" in text
    assert "TELEGRAM" in capsys.readouterr().out
