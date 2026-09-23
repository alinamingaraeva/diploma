"""Сравнение naive vs react на 5 музейных задачах (ДЗ 6.2)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_naive import run_agent as run_naive
from app.services.agent_react import run_react_with_reflection
from app.services import agent_naive as naive_mod

OUT = ROOT / "docs" / "agent-react-runs"

TASKS = [
    {
        "id": "01_simple_search",
        "kind": "простая, 1 tool",
        "task": "Какой телефон визит-центра Казанского Кремля? Ответь по базе знаний.",
    },
    {
        "id": "02_simple_time",
        "kind": "простая, 1 tool",
        "task": "Который сейчас час в часовом поясе Europe/Moscow? Нужна метка времени, не часы музея.",
    },
    {
        "id": "03_compose_rules_send",
        "kind": "средняя, composability",
        "task": (
            "Найди в базе правила входа с собакой на территорию Казанского Кремля "
            "и отправь краткую выжимку в Telegram-чат 12345."
        ),
    },
    {
        "id": "04_compose_phone_send",
        "kind": "средняя, composability",
        "task": (
            "Найди в базе телефон отдела экскурсий Казанского Кремля "
            "и отправь его посетителю в чат 55501."
        ),
    },
    {
        "id": "05_no_tool",
        "kind": "провокация, tool не нужен",
        "task": (
            "Поздравь меня коротким четверостишием с днём рождения. "
            "Не ищи ничего в базе музея и ничего никуда не отправляй — только стих."
        ),
    },
]


def _naive_tokens(result: dict) -> int:
    seen = {}
    for row in result.get("trace") or []:
        seen[row["step"]] = int(row.get("llm_input_tokens") or 0) + int(row.get("llm_output_tokens") or 0)
    return sum(seen.values())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in TASKS:
        print(f"\n=== {item['id']} naive ===", flush=True)
        naive = run_naive(item["task"])
        print(f"\n=== {item['id']} react ===", flush=True)
        react = run_react_with_reflection(item["task"])
        pack = {
            "id": item["id"],
            "kind": item["kind"],
            "task": item["task"],
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "naive": {
                "steps": naive.get("steps"),
                "error": naive.get("error"),
                "tools": [r["tool_name"] for r in naive.get("trace") or []],
                "tokens": _naive_tokens(naive),
                "answer": naive.get("answer") or "",
            },
            "react": {
                "steps": react.get("steps"),
                "error": react.get("error"),
                "tools": [r["tool_name"] for r in react.get("trace") or []],
                "tokens": (react.get("usage") or {}).get("total") or 0,
                "revisions": react.get("revisions") or 0,
                "answer": react.get("answer") or "",
                "verdicts": [r.get("verdict") for r in react.get("trace") or []],
            },
        }
        (OUT / f"{item['id']}.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        rows.append(pack)
        print("naive steps", pack["naive"]["steps"], "tokens", pack["naive"]["tokens"], "tools", pack["naive"]["tools"])
        print("react steps", pack["react"]["steps"], "tokens", pack["react"]["tokens"], "rev", pack["react"]["revisions"])
    (OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if naive_mod._RAG is not None:
        naive_mod._RAG.close()
        naive_mod._RAG = None
    print("saved", OUT)


if __name__ == "__main__":
    main()
