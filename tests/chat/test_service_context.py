from uuid import uuid4

from app.chat.context import build_context, count_tokens, fit_to_budget
from app.chat.domain import Chat, ChatMessage


def test_sliding_window_keeps_last():
    chat = Chat(owner_external_id="1", interface="cli", system_prompt="sys")
    history = [
        ChatMessage(chat_id=chat.id, role="user", content=str(i))
        for i in range(5)
    ]
    messages = build_context(chat, history, window=2)
    assert messages[0] == {"role": "system", "content": "sys"}
    assert [m["content"] for m in messages[1:]] == ["3", "4"]


def test_fit_to_budget_keeps_system():
    messages = [
        {"role": "system", "content": "keep"},
        {"role": "user", "content": "old " * 200},
        {"role": "user", "content": "new"},
    ]
    fitted = fit_to_budget(messages, budget=count_tokens([messages[0], messages[2]]) + 10)
    assert fitted[0]["role"] == "system"
    assert fitted[-1]["content"] == "new"
