from __future__ import annotations

import json
from pathlib import Path

KB_PATH = Path(__file__).resolve().parents[2] / "data" / "museum_kb.json"


def _load_kb() -> dict:
    return json.loads(KB_PATH.read_text(encoding="utf-8"))


def get_opening_hours(museum: str = "") -> str:
    kb = _load_kb()
    hours = kb.get("hours", [])
    needle = (museum or "").strip().lower()
    if needle:
        matched = [h for h in hours if needle in h["name"].lower() or needle in h["id"].lower()]
        if matched:
            hours = matched
        else:
            return json.dumps(
                {"found": False, "message": "Такой площадки нет в базе музея", "query": museum},
                ensure_ascii=False,
            )
    return json.dumps({"source": kb["source"], "hours": hours}, ensure_ascii=False)


def get_ticket_link(museum_or_event: str = "") -> str:
    kb = _load_kb()
    return json.dumps(
        {
            "url": kb["tickets_url"],
            "note": "Официальная касса музеев Казанского Кремля",
            "for": museum_or_event or "все музеи и выставки",
        },
        ensure_ascii=False,
    )


def search_museum_info(query: str) -> str:
    kb = _load_kb()
    q = (query or "").lower()
    hits = []
    for page in kb.get("pages", []):
        blob = f"{page['title']} {page['text']}".lower()
        if any(part in blob for part in q.split()) or q in blob:
            hits.append(page)
    if not hits and q:
        hits = kb.get("pages", [])[:2]
    return json.dumps({"source": kb["source"], "results": hits[:5]}, ensure_ascii=False)


HANDLERS = {
    "get_opening_hours": get_opening_hours,
    "get_ticket_link": get_ticket_link,
    "search_museum_info": search_museum_info,
}


def execute_tool(name: str, arguments: dict) -> str:
    handler = HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"unknown tool {name}"}, ensure_ascii=False)
    return handler(**{k: v for k, v in arguments.items() if k in handler.__code__.co_varnames})
