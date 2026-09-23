"""Два агента researcher → writer. create_supervisor на Polza даёт 502 на handoff-tools."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import Command

from experiments.common import (
    QUESTIONS,
    last_text,
    make_model,
    search_knowledge_base,
    usage_from_messages,
)

RESEARCHER = (
    "Ты researcher музеев Казанского Кремля. "
    "Ищи факты только через search_knowledge_base. "
    "Верни маркированный список [1], [2] с источником и короткой цитатой. "
    "Финальный ответ посетителю НЕ пиши. Если база пуста — так и скажи."
)
WRITER = (
    "Ты writer. Тебе передали факты researcher. "
    "Собери связный ответ на русском. Номера [1], [2] из фактов обязательно оставь в тексте. "
    "Не выдумывай телефоны. Если фактов нет или «в базе пусто» — честно скажи, что в документах музея этого нет. "
    "Tools не вызывай."
)

THREAD = "exp-langgraph"


def _new_messages(before: list, after: list) -> list:
    if after[: len(before)] == before:
        return after[len(before) :]
    return after[-1:] if after else []


def build_graph():
    model = make_model()
    researcher = create_agent(
        model=model,
        tools=[search_knowledge_base],
        system_prompt=RESEARCHER,
        name="researcher",
    )
    writer = create_agent(
        model=model,
        tools=[],
        system_prompt=WRITER,
        name="writer",
    )

    def run_researcher(state: MessagesState):
        before = list(state.get("messages") or [])
        out = researcher.invoke({"messages": before})
        return Command(update={"messages": _new_messages(before, out.get("messages") or [])}, goto="writer")

    def run_writer(state: MessagesState):
        before = list(state.get("messages") or [])
        out = writer.invoke({"messages": before})
        return Command(update={"messages": _new_messages(before, out.get("messages") or [])}, goto=END)

    builder = StateGraph(MessagesState)
    builder.add_node("researcher", run_researcher)
    builder.add_node("writer", run_writer)
    builder.add_edge(START, "researcher")
    # Статические рёбра — для mermaid; в runtime маршрут задаёт Command(goto=...).
    builder.add_edge("researcher", "writer")
    builder.add_edge("writer", END)
    return builder.compile(checkpointer=InMemorySaver())


def run_question(graph, item: dict, *, verbose: bool = True) -> dict:
    last_error = None
    for attempt in range(1, 4):
        config = {
            "configurable": {"thread_id": f"{THREAD}-{item['id']}-t{attempt}"},
            "recursion_limit": 15,
        }
        handoffs = 0
        t0 = time.perf_counter()
        try:
            for update in graph.stream(
                {"messages": [HumanMessage(content=item["question"])]},
                config,
                stream_mode="updates",
            ):
                if verbose:
                    keys = list(update.keys()) if isinstance(update, dict) else [str(update)]
                    print(f"  update {keys}", flush=True)
                if isinstance(update, dict) and ("researcher" in update or "writer" in update):
                    handoffs += 1
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            snap = graph.get_state(config)
            messages = (snap.values or {}).get("messages") or []
            tokens, calls = usage_from_messages(messages)
            return {
                "impl": "multi",
                "id": item["id"],
                "kind": item["kind"],
                "question": item["question"],
                "total_tokens": tokens,
                "llm_calls": calls,
                "latency_ms": latency_ms,
                "handoff_count": handoffs,
                "answer": last_text(messages),
            }
        except Exception as exc:
            last_error = exc
            err = str(exc)
            if "502" not in err and "BAD_GATEWAY" not in err:
                raise
            print(f"  retry {attempt} after 502", flush=True)
            time.sleep(2 * attempt)
    raise last_error


def save_mermaid(graph) -> None:
    path = ROOT / "docs" / "architecture-multi-agent.md"
    mermaid = graph.get_graph().draw_mermaid()
    path.write_text(
        "# Мультиагент researcher → writer (ДЗ 6.5)\n\n"
        "Сначала пробовали `langgraph_supervisor.create_supervisor`: на Polza handoff-tools "
        "дают 502 «некорректный вызов инструмента». Рабочий вариант — ручной граф "
        "`Command(goto=...)`: START → researcher → writer → END. "
        "InMemorySaver, thread_id префикс `exp-langgraph`.\n\n"
        "```mermaid\n"
        f"{mermaid.strip()}\n"
        "```\n",
        encoding="utf-8",
    )
    print("wrote", path)


def main() -> None:
    graph = build_graph()
    save_mermaid(graph)
    for item in QUESTIONS:
        print(f"\n=== multi {item['id']} ===", flush=True)
        row = run_question(graph, item)
        print(row["answer"][:400], flush=True)
        print(
            f"tokens={row['total_tokens']} calls={row['llm_calls']} "
            f"lat={row['latency_ms']} handoff={row['handoff_count']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
