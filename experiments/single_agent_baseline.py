"""Один create_agent с тем же search_knowledge_base. Baseline ДЗ 6.5."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from experiments.common import (
    QUESTIONS,
    last_text,
    make_model,
    search_knowledge_base,
    usage_from_messages,
)

PROMPT = (
    "Ты консультант музеев Казанского Кремля. "
    "Найди факты через search_knowledge_base и оформи связный ответ на русском "
    "с цитированием источников [1], [2], как их вернул tool. "
    "Не выдумывай телефоны. Если tool сказал «в базе пусто» — так и ответь посетителю."
)


def build_graph():
    return create_agent(
        model=make_model(),
        tools=[search_knowledge_base],
        system_prompt=PROMPT,
        name="museum_single",
    )


def run_question(graph, item: dict, *, verbose: bool = True) -> dict:
    config = {
        "configurable": {"thread_id": f"exp-single-{item['id']}"},
        "recursion_limit": 15,
    }
    t0 = time.perf_counter()
    result = graph.invoke({"messages": [HumanMessage(content=item["question"])]}, config)
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    messages = result.get("messages") or []
    tokens, calls = usage_from_messages(messages)
    if verbose:
        print(f"  done {item['id']}", flush=True)
    return {
        "impl": "single",
        "id": item["id"],
        "kind": item["kind"],
        "question": item["question"],
        "total_tokens": tokens,
        "llm_calls": calls,
        "latency_ms": latency_ms,
        "handoff_count": 0,
        "answer": last_text(messages),
    }


def main() -> None:
    graph = build_graph()
    for item in QUESTIONS:
        print(f"\n=== single {item['id']} ===", flush=True)
        row = run_question(graph, item)
        print(row["answer"][:400], flush=True)
        print(f"tokens={row['total_tokens']} calls={row['llm_calls']} lat={row['latency_ms']}", flush=True)


if __name__ == "__main__":
    main()
