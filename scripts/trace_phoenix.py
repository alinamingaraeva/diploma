"""20+ запросов в RAG, чтобы в Phoenix появились LlamaIndex-трейсы."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.observability.tracing import setup_tracing
from app.services.rag import RAGService

QUESTIONS = [
    "Какой телефон визит-центра Казанского Кремля?",
    "Где купить билет в музеи Казанского Кремля?",
    "Сколько стоит взрослый билет в Музей естественной истории?",
    "Какие телефоны у центра Эрмитаж-Казань?",
    "До скольких открыта мечеть Кул-Шариф?",
    "Круглосуточно ли работает проход через Спасскую башню?",
    "Какой телефон отдела экскурсий?",
    "Можно ли зайти на территорию Кремля с собакой?",
    "Какой день выходной в музеях зимой 2025–2026?",
    "Какая выставка идёт в Эрмитаж-Казань?",
    "Что дороже для взрослого: Эрмитаж-Казань или Пушечный двор?",
    "В пятницу вечером хочу в Эрмитаж-Казань: во сколько открыто и сколько стоит взрослый билет?",
    "Куда звонить в визит-центр и где купить билет онлайн?",
    "Пустят ли собаку внутрь здания Эрмитажа-Казань?",
    "Можно ли туристу зайти в Кул-Шариф в пятницу во время джума-намаза?",
    "Где смотреть актуальную афишу?",
    "В каком здании находится Музей естественной истории?",
    "Есть ли экскурсии по Пушкинской карте?",
    "Какой адрес музея-заповедника Казанский Кремль?",
    "Как доехать до Кремля на метро?",
    "Сколько стоит взрослый билет в Пушечный двор?",
    "Кто выиграл чемпионат мира по футболу в 2018 году?",
]


def main() -> None:
    setup_tracing(project_name="diploma-fastapi")
    service = RAGService()
    try:
        service.build()
        for question in QUESTIONS:
            result = service.evaluate_inputs(question)
            print(json.dumps({"q": question, "score": result.get("top_score"), "ok": result.get("confident")}, ensure_ascii=False))
    finally:
        service.close()
    print(f"sent {len(QUESTIONS)} traces; UI http://localhost:6006")


if __name__ == "__main__":
    main()
