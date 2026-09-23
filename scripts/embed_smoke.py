"""Smoke: повторный вызов не ходит в API (кеш). Запуск: python -m scripts.embed_smoke"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.services.embeddings import EmbeddingService, cosine


def main() -> None:
    bench_path = Path("tests/eval/mini_benchmark.json")
    pairs = json.loads(bench_path.read_text(encoding="utf-8"))
    service = EmbeddingService()
    sample = [pairs[0]["query"], pairs[0]["relevant"], pairs[0]["irrelevant"]]
    cost = service.estimate_index_cost(sample * 20)
    print("cost_preview_50_docs_like:", cost)

    t0 = time.perf_counter()
    first = service.embed_texts(sample)
    t1 = time.perf_counter()
    calls_after_first = service.api_calls
    second = service.embed_texts(sample)
    t2 = time.perf_counter()
    print(
        json.dumps(
            {
                "dim": len(first[0]),
                "api_calls_first": calls_after_first,
                "api_calls_total_after_second": service.api_calls,
                "seconds_first": round(t1 - t0, 3),
                "seconds_second": round(t2 - t1, 3),
                "cache_hit_expected": service.api_calls == calls_after_first,
                "relevant_score": round(cosine(first[0], first[1]), 3),
                "irrelevant_score": round(cosine(first[0], first[2]), 3),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    assert second == first
    assert service.api_calls == calls_after_first
    service.close()


if __name__ == "__main__":
    main()
