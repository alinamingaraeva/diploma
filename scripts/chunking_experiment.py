"""Прогон chunking-стратегий, метрик и re-ranker (ДЗ 5.4)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from llama_index.core import SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.services.chunking import ChunkStrategy, get_splitter
from app.services.llama_setup import configure_llama
from app.services.rag_common import make_sync_http_client, qdrant_api_key
from app.services.retrieval_eval import evaluate_retrieval
from app.services.reranker import BgeReranker

DATASET = Path("tests/eval/retrieval_dataset.json")
OUT_PATH = Path("var/chunking_results.json")
COLLECTIONS = {
    "fixed": "docs_fixed",
    "recursive": "docs_recursive",
    "semantic": "docs_semantic",
}


def load_dataset() -> list[dict]:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def chunk_stats(nodes, n_docs: int) -> dict:
    lengths = [len(node.get_content() or "") for node in nodes]
    return {
        "chunks": len(nodes),
        "chunks_per_doc": round(len(nodes) / max(n_docs, 1), 2),
        "avg_chars": round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
    }


def recreate_index(client: QdrantClient, name: str, nodes):
    existing = {item.name for item in client.get_collections().collections}
    if name in existing:
        client.delete_collection(name)
    store = QdrantVectorStore(client=client, collection_name=name)
    storage = StorageContext.from_defaults(vector_store=store)
    return VectorStoreIndex(nodes, storage_context=storage, show_progress=True)


def retrieve_batch(index: VectorStoreIndex, questions: list[str], top_k: int):
    retriever = index.as_retriever(similarity_top_k=top_k)
    rows = []
    elapsed = []
    for question in questions:
        started = time.perf_counter()
        nodes = retriever.retrieve(question)
        elapsed.append((time.perf_counter() - started) * 1000)
        rows.append(nodes)
    avg_ms = round(sum(elapsed) / len(elapsed), 1) if elapsed else 0.0
    return rows, avg_ms


def main() -> None:
    settings = get_settings()
    dataset = load_dataset()
    questions = [row["question"] for row in dataset]
    gold = [row["relevant_doc_ids"] for row in dataset]
    http = make_sync_http_client(settings)
    embed_model = configure_llama(settings, http)
    documents = SimpleDirectoryReader(str(settings.rag_data_dir), recursive=True).load_data()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=qdrant_api_key(settings),
        check_compatibility=False,
    )
    report: dict = {"strategies": [], "grid": [], "rerank": []}

    for strategy in ("fixed", "recursive", "semantic"):
        splitter = get_splitter(
            strategy,  # type: ignore[arg-type]
            chunk_size=512,
            chunk_overlap=64,
            embed_model=embed_model,
        )
        nodes = splitter.get_nodes_from_documents(documents)
        stats = chunk_stats(nodes, len(documents))
        print(f"index {strategy} {stats}")
        index = recreate_index(client, COLLECTIONS[strategy], nodes)
        retrieved, avg_ms = retrieve_batch(index, questions, top_k=10)
        metrics = evaluate_retrieval(retrieved, gold)
        row = {
            "strategy": strategy,
            "collection": COLLECTIONS[strategy],
            **stats,
            **metrics,
            "retrieval_ms": avg_ms,
        }
        report["strategies"].append(row)
        print(row)

    best = max(report["strategies"], key=lambda item: (item["hit_rate@5"], item["mrr@10"]))
    print("best_strategy", best["strategy"])

    if best["strategy"] != "semantic":
        grids = [(256, 32), (256, 64), (512, 32), (512, 64)]
        for chunk_size, overlap in grids:
            name = f"docs_grid_{best['strategy']}_{chunk_size}_{overlap}"
            splitter = get_splitter(
                best["strategy"],  # type: ignore[arg-type]
                chunk_size=chunk_size,
                chunk_overlap=overlap,
                embed_model=embed_model,
            )
            nodes = splitter.get_nodes_from_documents(documents)
            index = recreate_index(client, name, nodes)
            for top_k in (10, 20) if (chunk_size, overlap) == (512, 64) else (10,):
                retrieved, avg_ms = retrieve_batch(index, questions, top_k=top_k)
                metrics = evaluate_retrieval(retrieved, gold)
                report["grid"].append(
                    {
                        "strategy": best["strategy"],
                        "chunk_size": chunk_size,
                        "overlap": overlap,
                        "top_k": top_k,
                        **metrics,
                        "retrieval_ms": avg_ms,
                    }
                )
                print(report["grid"][-1])
            client.delete_collection(name)
    else:
        for top_k in (10, 20):
            index = VectorStoreIndex.from_vector_store(
                QdrantVectorStore(client=client, collection_name="docs_semantic")
            )
            retrieved, avg_ms = retrieve_batch(index, questions, top_k=top_k)
            metrics = evaluate_retrieval(retrieved, gold)
            report["grid"].append(
                {
                    "strategy": "semantic",
                    "chunk_size": None,
                    "overlap": None,
                    "top_k": top_k,
                    **metrics,
                    "retrieval_ms": avg_ms,
                }
            )

    winner = max(
        report["grid"] or report["strategies"],
        key=lambda item: (item["hit_rate@5"], item["mrr@10"]),
    )
    print("winner_config", winner)

    rerank_strategy: ChunkStrategy = winner.get("strategy") or best["strategy"]
    chunk_size = int(winner.get("chunk_size") or 512)
    overlap = int(winner.get("overlap") or 64)
    retrieve_k = 20
    splitter = get_splitter(
        rerank_strategy,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        embed_model=embed_model,
    )
    index = recreate_index(client, COLLECTIONS.get(rerank_strategy, "docs_recursive"), splitter.get_nodes_from_documents(documents))
    retrieved, avg_ms = retrieve_batch(index, questions, top_k=retrieve_k)
    baseline = evaluate_retrieval(retrieved, gold)
    report["rerank"].append({"label": "best_without_rerank", **baseline, "retrieval_ms": avg_ms, "top_k": retrieve_k})

    print("loading reranker BAAI/bge-reranker-v2-m3")
    reranker = BgeReranker(settings.rag_rerank_model)
    reranked_rows = []
    started = time.perf_counter()
    for question, nodes in zip(questions, retrieved):
        reranked_rows.append(reranker.rerank(question, nodes, top_n=10))
    rerank_ms = round((time.perf_counter() - started) * 1000 / max(len(questions), 1), 1)
    rerank_metrics = evaluate_retrieval(reranked_rows, gold)
    report["rerank"].append(
        {
            "label": "best_with_rerank",
            **rerank_metrics,
            "retrieval_ms": round(avg_ms + rerank_ms, 1),
            "rerank_ms": rerank_ms,
            "top_k": 10,
        }
    )
    print(report["rerank"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT_PATH)
    http.close()
    client.close()


if __name__ == "__main__":
    main()
