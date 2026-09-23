from bot.services.streaming import _last_edit_at, _should_edit


def test_edit_debounce_skips_second_call():
    _last_edit_at.clear()
    assert _should_edit(42) is True
    assert _should_edit(42) is False
    _last_edit_at[42] = 0.0
    assert _should_edit(42) is True
    _last_edit_at.clear()
