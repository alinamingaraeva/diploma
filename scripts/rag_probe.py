"""Пять контрольных вопросов ДЗ 5.3. Коллекция уже должна быть в Qdrant."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.rag import RAGService

QUESTIONS = [
    ("good", "Какой телефон визит-центра Казанского Кремля?"),
    ("good", "Где купить билет в Эрмитаж-Казань?"),
    ("good", "Можно ли зайти на территорию Кремля с собакой?"),
    (
        "medium",
        "В пятницу вечером хочу в Эрмитаж-Казань: во сколько открыто и сколько стоит взрослый билет?",
    ),
    ("out", "Кто выиграл чемпионат мира по футболу в 2018 году?"),
]


def main() -> None:
    service = RAGService()
    try:
        service.build()
        rows = []
        for kind, question in QUESTIONS:
            result = service.answer(question)
            top = result["sources"][0] if result["sources"] else {}
            rows.append(
                {
                    "kind": kind,
                    "question": question,
                    "answer": result["answer"],
                    "top_score": result["top_score"],
                    "top_source": top.get("source"),
                    "sources": [item["source"] for item in result["sources"]],
                }
            )
            print(json.dumps(rows[-1], ensure_ascii=False, indent=2))
            print("---")
    finally:
        service.close()


if __name__ == "__main__":
    main()
