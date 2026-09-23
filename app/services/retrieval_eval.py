"""Hit Rate@5, MRR@10, Recall@10 по golden dataset."""

from __future__ import annotations

from collections.abc import Sequence


def _source_of(node) -> str:
    if isinstance(node, str):
        return node
    meta = getattr(node, "metadata", None) or {}
    return str(meta.get("file_name") or meta.get("filename") or meta.get("source") or "")


def evaluate_retrieval(
    retrieved: Sequence[Sequence[object]],
    relevant_doc_ids: Sequence[Sequence[str]],
    hit_k: int = 5,
    mrr_k: int = 10,
    recall_k: int = 10,
) -> dict[str, float]:
    if len(retrieved) != len(relevant_doc_ids):
        raise ValueError("retrieved и relevant_doc_ids разной длины")
    hits = 0
    mrr_sum = 0.0
    recall_sum = 0.0
    n = len(retrieved)
    if n == 0:
        return {"hit_rate@5": 0.0, "mrr@10": 0.0, "recall@10": 0.0}
    for ranked, gold in zip(retrieved, relevant_doc_ids):
        gold_set = {item for item in gold if item}
        sources = [_source_of(node) for node in ranked]
        top_hit = sources[:hit_k]
        if gold_set.intersection(top_hit):
            hits += 1
        rank = None
        for i, source in enumerate(sources[:mrr_k], start=1):
            if source in gold_set:
                rank = i
                break
        if rank is not None:
            mrr_sum += 1.0 / rank
        top_recall = set(sources[:recall_k])
        if gold_set:
            recall_sum += len(gold_set.intersection(top_recall)) / len(gold_set)
    return {
        "hit_rate@5": round(hits / n, 4),
        "mrr@10": round(mrr_sum / n, 4),
        "recall@10": round(recall_sum / n, 4),
    }
