import tiktoken
from typing import List, Dict, Any
from app.chat.domain import Chat, ChatMessage

# --- Стратегия Sliding Window ---
def build_context(chat: Chat, history: List[ChatMessage], strategy: str = "sliding") -> List[Dict[str, str]]:
    messages = []
    if chat.system_prompt:
        messages.append({"role": "system", "content": chat.system_prompt})
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    return messages

# --- Подсчёт токенов ---
def count_tokens(messages: List[Dict[str, str]]) -> int:
    encoding = tiktoken.get_encoding("o200k_base")
    text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    return len(encoding.encode(text)) + 4 * len(messages) + 2

# --- Обрезка до бюджета ---
def fit_to_budget(messages: List[Dict[str, str]], budget: int) -> List[Dict[str, str]]:
    # Если уже влезает — возвращаем как есть
    if count_tokens(messages) <= budget:
        return messages

    # Сохраняем system-сообщение (если есть)
    system = []
    rest = []
    for m in messages:
        if m["role"] == "system":
            system.append(m)
        else:
            rest.append(m)

    # Обрезаем rest с начала (старые сообщения)
    while rest and count_tokens(system + rest) > budget:
        rest.pop(0)

    return system + rest