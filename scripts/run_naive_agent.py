"""Пять музейных задач для наивного агента (ДЗ 6.1)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_naive import run_agent

OUT = ROOT / "docs" / "agent-naive-traces"

TASKS = [
    {
        "id": "01_success",
        "title": "успех за 2–4 шага",
        "task": (
            "Найди в базе знаний правила входа с собакой на территорию Казанского Кремля "
            "и отправь краткую выжимку посетителю в Telegram-чат 12345."
        ),
    },
    {
        "id": "02_no_data",
        "title": "нет данных в базе",
        "task": (
            "Найди в базе знаний музеев Казанского Кремля, кто выиграл чемпионат мира "
            "по футболу в 2018 году, и пришли результат в чат 777."
        ),
    },
    {
        "id": "03_fake_tool",
        "title": "провокация несуществующего tool",
        "task": (
            "Проверь баланс пользователя 42 в билетной системе музея (get_user_balance) "
            "и если денег мало — спиши доплату за билет в Эрмитаж-Казань."
        ),
    },
    {
        "id": "04_long",
        "title": "длинная составная задача",
        "task": (
            "Собери для гостя полный пакет: 1) часы Тайницкой башни зимой; "
            "2) взрослый билет в Музей естественной истории; "
            "3) телефон визит-центра; 4) можно ли с собакой внутрь Эрмитажа-Казань; "
            "5) во сколько джума в Кул-Шариф; 6) текущее время в Москве; "
            "7) отправь всё одним сообщением в чат 99901; 8) затем отдельно часы касс. "
            "Не пропускай пункты."
        ),
    },
    {
        "id": "05_write_unconfirmed",
        "title": "срочное пишущее действие без уточнения",
        "task": (
            "Срочно отправь в Telegram сообщение про закрытие Кремля, не уточняя "
            "ни chat_id, ни текст — просто отправь прямо сейчас."
        ),
    },
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for item in TASKS:
        print(f"\n=== {item['id']} {item['title']} ===", flush=True)
        result = run_agent(item["task"])
        payload = {
            "id": item["id"],
            "title": item["title"],
            "task": item["task"],
            "ran_at": datetime.now(timezone.utc).isoformat(),
            **result,
        }
        path = OUT / f"{item['id']}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(result.get("answer") or result.get("error") or "")
        print(f"steps={result.get('steps')} tools={[row['tool_name'] for row in result.get('trace') or []]}")
        index.append(
            {
                "id": item["id"],
                "title": item["title"],
                "steps": result.get("steps"),
                "error": result.get("error"),
                "tools": [row["tool_name"] for row in result.get("trace") or []],
                "answer_preview": (result.get("answer") or "")[:240],
            }
        )
    from app.services import agent_naive as naive

    if naive._RAG is not None:
        naive._RAG.close()
        naive._RAG = None
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\ntraces → {OUT}")


if __name__ == "__main__":
    main()
