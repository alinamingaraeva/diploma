"""Локальный cross-encoder BAAI/bge-reranker-v2-m3."""

from __future__ import annotations

from typing import Any


class BgeReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        from sentence_transformers import CrossEncoder

        self.model_name = model_name
        self.model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        candidates: list[Any],
        top_n: int = 5,
        text_getter=None,
    ) -> list[Any]:
        if not candidates:
            return []
        getter = text_getter or _default_text
        pairs = [(query, getter(item)) for item in candidates]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(candidates, scores), key=lambda row: float(row[1]), reverse=True)
        result = []
        for item, score in ranked[: max(1, top_n)]:
            if hasattr(item, "score"):
                item.score = float(score)
            result.append(item)
        return result


def _default_text(item: Any) -> str:
    if hasattr(item, "get_content"):
        return item.get_content() or ""
    if isinstance(item, dict):
        return str(item.get("text") or "")
    return str(item)
