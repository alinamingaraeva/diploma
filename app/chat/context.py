from typing import Any

import tiktoken

from app.chat.domain import Chat, ChatMessage


def _content_to_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
            else:
                parts.append("[media]")
        return " ".join(parts)
    return str(content)


def build_context(
    chat: Chat,
    history: list[ChatMessage],
    strategy: str = "sliding",
    window: int = 10,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if chat.system_prompt:
        messages.append({"role": "system", "content": chat.system_prompt})
    recent = history[-window:] if window > 0 else history
    for msg in recent:
        if msg.media_refs and isinstance(msg.media_refs, dict) and msg.media_refs.get("part"):
            part = msg.media_refs["part"]
            content: Any = [{"type": "text", "text": msg.content}]
            if part.get("type") == "image_url":
                content.append(part)
            elif part.get("type") == "text":
                content.append({"type": "text", "text": part.get("text", "")})
            messages.append({"role": msg.role, "content": content})
        else:
            messages.append({"role": msg.role, "content": msg.content})
    return messages


def count_tokens(messages: list[dict[str, Any]]) -> int:
    encoding = tiktoken.get_encoding("o200k_base")
    text = "\n".join(f"{m.get('role')}: {_content_to_str(m.get('content'))}" for m in messages)
    return len(encoding.encode(text)) + 4 * len(messages) + 2


def fit_to_budget(messages: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    if count_tokens(messages) <= budget:
        return messages
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    while rest and count_tokens(system + rest) > budget:
        rest.pop(0)
    return system + rest
