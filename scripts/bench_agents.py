"""Бенчмарк: ReAct 6.2 vs custom StateGraph vs prebuilt create_agent."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.agent_graph import run_custom, run_prebuilt
from app.services.agent_react import run_react_with_reflection
from app.services import agent_naive as naive_mod
from scripts.run_react_compare import TASKS

OUT = ROOT / "docs" / "agent-graph-bench.json"
REPEATS = 3


def _react_pack(result: dict) -> dict:
    usage = result.get("usage") or {}
    return {
        "answer": (result.get("answer") or "")[:400],
        "steps": result.get("steps"),
        "prompt_tokens": int(usage.get("prompt") or 0),
        "completion_tokens": int(usage.get("completion") or 0),
        "error": result.get("error"),
    }


async def _one(impl: str, task: str, task_id: str) -> dict:
    t0 = time.perf_counter()
    if impl == "react":
        raw = await asyncio.to_thread(run_react_with_reflection, task)
        pack = _react_pack(raw)
    elif impl == "custom":
        raw = await run_custom(task, thread_id=f"bench-{task_id}")
        pack = {
            "answer": (raw.get("answer") or "")[:400],
            "steps": raw.get("steps"),
            "prompt_tokens": int((raw.get("usage") or {}).get("prompt") or 0),
            "completion_tokens": int((raw.get("usage") or {}).get("completion") or 0),
            "error": None,
        }
    else:
        raw = await run_prebuilt(task, thread_id=f"bench-prebuilt-{task_id}")
        pack = {
            "answer": (raw.get("answer") or "")[:400],
            "steps": raw.get("steps"),
            "prompt_tokens": int((raw.get("usage") or {}).get("prompt") or 0),
            "completion_tokens": int((raw.get("usage") or {}).get("completion") or 0),
            "error": None,
        }
    pack["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    pack["impl"] = impl
    pack["task_id"] = task_id
    return pack


def _mean(rows: list[dict], key: str) -> float:
    vals = [float(r[key] or 0) for r in rows]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


async def _run() -> list[dict]:
    summary: list[dict] = []
    all_runs: list[dict] = []
    for item in TASKS:
        for impl in ("react", "custom", "prebuilt"):
            repeats = []
            for rep in range(1, REPEATS + 1):
                print(f"\n=== {item['id']} {impl} #{rep} ===", flush=True)
                row = await _one(impl, item["task"], f"{item['id']}-{impl}-{rep}")
                row["repeat"] = rep
                row["kind"] = item["kind"]
                repeats.append(row)
                all_runs.append(row)
                print(
                    f"  {row['latency_ms']} ms steps={row['steps']} "
                    f"tok={row['prompt_tokens']}+{row['completion_tokens']}",
                    flush=True,
                )
                OUT.write_text(
                    json.dumps(
                        {"ran_at": datetime.now(timezone.utc).isoformat(), "runs": all_runs, "summary": summary},
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            summary.append(
                {
                    "id": item["id"],
                    "kind": item["kind"],
                    "task": item["task"],
                    "impl": impl,
                    "latency_ms": _mean(repeats, "latency_ms"),
                    "prompt_tokens": _mean(repeats, "prompt_tokens"),
                    "completion_tokens": _mean(repeats, "completion_tokens"),
                    "total_steps": _mean(repeats, "steps"),
                    "answers": [r.get("answer") or "" for r in repeats],
                }
            )
    OUT.write_text(
        json.dumps(
            {"ran_at": datetime.now(timezone.utc).isoformat(), "runs": all_runs, "summary": summary},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    asyncio.run(_run())
    if naive_mod._RAG is not None:
        naive_mod._RAG.close()
        naive_mod._RAG = None
    print("saved", OUT)


if __name__ == "__main__":
    main()
