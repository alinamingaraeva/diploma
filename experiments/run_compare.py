"""Прогон single vs multi на 5 вопросах → experiments/results.json."""

from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.common import (
    QUESTIONS,
    close_rag,
    has_citation,
    heuristic_quality,
    judge_quality,
    make_model,
)
from experiments.multi_agent_langgraph import build_graph as build_multi
from experiments.multi_agent_langgraph import run_question as run_multi
from experiments.multi_agent_langgraph import save_mermaid
from experiments.single_agent_baseline import build_graph as build_single
from experiments.single_agent_baseline import run_question as run_single

OUT = ROOT / "experiments" / "results.json"


def _p50(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(statistics.median(values)), 1)


def main() -> None:
    judge_model = make_model()
    single = build_single()
    multi = build_multi()
    save_mermaid(multi)
    rows = []
    for item in QUESTIONS:
        print(f"\n===== {item['id']} single =====", flush=True)
        s = run_single(single, item)
        s["has_citation"] = has_citation(s["answer"])
        s["quality_heuristic"] = heuristic_quality(item["id"], s["answer"])
        s["quality"] = judge_quality(item["question"], s["answer"], judge_model, item["id"])
        rows.append(s)
        print("quality", s["quality"], "heuristic", s["quality_heuristic"], "cite", s["has_citation"], flush=True)

        print(f"\n===== {item['id']} multi =====", flush=True)
        try:
            m = run_multi(multi, item)
        except Exception as exc:
            print("  FAIL", type(exc).__name__, flush=True)
            m = {
                "impl": "multi",
                "id": item["id"],
                "kind": item["kind"],
                "question": item["question"],
                "total_tokens": 0,
                "llm_calls": 0,
                "latency_ms": 0,
                "handoff_count": 0,
                "answer": f"ERROR: {exc}",
            }
        m["has_citation"] = has_citation(m.get("answer") or "")
        m["quality_heuristic"] = heuristic_quality(item["id"], m.get("answer") or "")
        m["quality"] = judge_quality(item["question"], m.get("answer") or "", judge_model, item["id"])
        rows.append(m)
        print("quality", m["quality"], "cite", m["has_citation"], "handoff", m["handoff_count"], flush=True)
        OUT.write_text(
            json.dumps({"rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    summary = {}
    for impl in ("single", "multi"):
        part = [r for r in rows if r["impl"] == impl]
        summary[impl] = {
            "tokens_mean": round(sum(r["total_tokens"] for r in part) / len(part), 1),
            "llm_calls_mean": round(sum(r["llm_calls"] for r in part) / len(part), 2),
            "latency_p50_ms": _p50([r["latency_ms"] for r in part]),
            "handoff_mean": round(sum(r["handoff_count"] for r in part) / len(part), 2),
            "quality_mean": round(sum(r["quality"] for r in part) / len(part), 2),
            "quality_heuristic_mean": round(
                sum(r.get("quality_heuristic", 0) for r in part) / len(part), 2
            ),
        }
    pack = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "rows": rows,
    }
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    close_rag()
    print("saved", OUT)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
