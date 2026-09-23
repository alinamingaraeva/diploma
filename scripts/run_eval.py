"""Прогон golden dataset через RAG + RAGAS 0.4."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from app.core.config import get_settings
from app.eval.metrics import build_metrics, eval_row
from app.services.rag import RAGService

DEFAULT_GOLDEN = ROOT / "tests" / "eval" / "golden_dataset.json"
DEFAULT_OUT = ROOT / "tests" / "eval" / "results"


def _load_golden(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) < 1:
        raise SystemExit(f"Пустой датасет: {path}")
    return payload


async def _score_one(sem, metrics, rag: RAGService, item: dict) -> dict:
    async with sem:
        question = item["user_input"]
        packed = await asyncio.to_thread(rag.evaluate_inputs, question)
        scores = await eval_row(
            metrics,
            user_input=question,
            response=packed.get("answer") or "",
            retrieved_contexts=packed.get("retrieved_contexts") or [],
            reference=item.get("reference") or "",
        )
        print(
            f"ok {question[:70]!r} faith={scores['faithfulness']:.2f} rel={scores['answer_relevancy']:.2f} cite={scores['has_citation']:.0f}",
            flush=True,
        )
        return {
            "user_input": question,
            "reference": item.get("reference") or "",
            "response": packed.get("answer") or "",
            "retrieved_contexts": " || ".join(packed.get("retrieved_contexts") or []),
            "top_score": packed.get("top_score"),
            "confident": packed.get("confident"),
            "latency_ms": packed.get("latency_ms"),
            **scores,
        }


async def run(golden: Path, label: str, out_dir: Path) -> Path:
    settings = get_settings()
    dataset = _load_golden(golden)
    rag = RAGService(settings)
    metrics = None
    try:
        rag.build()
        metrics = build_metrics(settings)
        sem = asyncio.Semaphore(max(1, settings.eval_concurrency))
        rows = await asyncio.gather(*[_score_one(sem, metrics, rag, item) for item in dataset])
    finally:
        rag.close()
        if metrics and metrics.get("client"):
            await metrics["client"].close()
    frame = pd.DataFrame(rows)
    numeric = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "has_citation",
        "latency_ms",
    ]
    summary = {col: float(frame[col].mean()) for col in numeric if col in frame}
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{stamp}_{label}.csv"
    json_path = out_dir / f"{stamp}_{label}.json"
    frame.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(csv_path)
    return csv_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--label", default="baseline")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    asyncio.run(run(args.golden, args.label, args.out))


if __name__ == "__main__":
    main()
