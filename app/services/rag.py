"""Корпоративный RAG: retrieve → score-guard → цитаты [1], [2]."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from openai import OpenAI
from qdrant_client import QdrantClient

from app.core.config import Settings as AppSettings, get_settings
from app.services.llama_setup import configure_llama
from app.services.official_site import OfficialSiteRetriever, OfficialSource
from app.services.rag_common import make_sync_http_client, qdrant_api_key

logger = structlog.get_logger(__name__)

REFUSAL = "по базе не нашёл, могу эскалировать"

CITE_PROMPT = (
    "Ты консультант музеев Казанского Кремля. Отвечай только по пронумерованному контексту. "
    "В каждом ответе ставь хотя бы одну ссылку вида [1] или [2] на фрагмент, из которого взял факт. "
    "Если цена, телефон, часы или правило есть хотя бы в одном фрагменте — ответь по ним, не отказывайся. "
    "Нельзя в одном ответе и давать факт, и писать отказ. "
    "Отказ дословно «по базе не нашёл, могу эскалировать» — только если в контексте нет данных по теме. "
    "Не выдумывай телефоны, цены и часы."
)

LIVE_CITE_PROMPT = (
    "Ты консультант музеев Казанского Кремля. Отвечай только по свежему контексту с официального сайта "
    "kazan-kremlin.ru и обязательно указывай ссылку на источник в виде [1] или [2]. "
    "Для вопросов со словами «сегодня», «в эти выходные», «сейчас» учитывай указанную текущую дату. "
    "Отличай временную выставку от постоянной экспозиции, экскурсии, квеста, мастер-класса и шоу. "
    "Если названный музей отсутствует в разделе «Выставки в музеях» свежей недельной афиши, так и скажи: "
    "в официальной афише на эти даты отдельная временная выставка не указана. Затем перечисли программы "
    "этого музея на нужные даты, если они есть. Сохраняй все даты и часы из источника: если программа "
    "указана сразу на два дня, не пропускай ни один из них. Не делай вывод, что музей закрыт, без прямого указания. "
    "Не используй общие знания, сторонние сайты и сведения из старых новостей."
)


class RAGService:
    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or get_settings()
        self._http = make_sync_http_client(self.settings)
        self._qdrant: QdrantClient | None = None
        self._index: VectorStoreIndex | None = None
        self._reranker = None
        self.llm = OpenAI(
            api_key=self.settings.openai.api_key.get_secret_value(),
            base_url=self.settings.openai.base_url,
            http_client=self._http,
            timeout=self.settings.openai.request_timeout,
            max_retries=self.settings.openai.max_retries,
        )
        self.official_site = (
            OfficialSiteRetriever(
                self._http,
                base_url=self.settings.official_site_base_url,
                cache_ttl_seconds=self.settings.official_site_cache_ttl_seconds,
                timeout_seconds=self.settings.official_site_timeout_seconds,
            )
            if self.settings.official_site_enabled
            else None
        )

    def _qdrant_client(self) -> QdrantClient:
        if self._qdrant is None:
            self._qdrant = QdrantClient(
                url=self.settings.qdrant_url,
                api_key=qdrant_api_key(self.settings),
                check_compatibility=False,
            )
        return self._qdrant

    def build(self) -> None:
        configure_llama(self.settings, self._http)
        vector_store = QdrantVectorStore(
            client=self._qdrant_client(),
            collection_name=self.settings.rag_collection,
        )
        storage = StorageContext.from_defaults(vector_store=vector_store)
        self._index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage)

    def _condense(self, question: str, history: list[dict] | None) -> str:
        if not history:
            return question
        turns = []
        for item in history[-8:]:
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            turns.append(f"{role}: {item.get('content') or ''}")
        if not turns:
            return question
        completion = self.llm.chat.completions.create(
            model=self.settings.openai.default_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Перепиши последний вопрос посетителя в самодостаточный запрос к базе "
                        "музеев Казанского Кремля. Сохрани язык и интент из истории "
                        "(телефон, часы, билеты, правила и т.д.). "
                        "Пример: история про телефон визит-центра + «а для экскурсий?» → "
                        "«Какой телефон отдела экскурсий Казанского Кремля?». "
                        "Верни только переписанный вопрос, без кавычек и пояснений."
                    ),
                },
                {
                    "role": "user",
                    "content": "История:\n" + "\n".join(turns) + f"\n\nПоследний вопрос: {question}",
                },
            ],
        )
        rewritten = (completion.choices[0].message.content or question).strip().strip('"«»')
        logger.info("rag_condense", original=question[:120], rewritten=rewritten[:160])
        return rewritten or question

    def _format_sources(self, nodes) -> list[dict]:
        sources = []
        for index, node in enumerate(nodes, start=1):
            inner = getattr(node, "node", node)
            meta = dict(getattr(inner, "metadata", None) or getattr(node, "metadata", None) or {})
            raw = ""
            if hasattr(node, "get_content"):
                raw = node.get_content() or ""
            elif hasattr(inner, "get_content"):
                raw = inner.get_content() or ""
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="replace")
            page = meta.get("page") if meta.get("page") not in (None, "") else meta.get("page_label")
            if page is not None:
                try:
                    page = int(page)
                except (TypeError, ValueError):
                    page = str(page)
            snippet = str(raw).replace("\r\n", "\n").replace("\r", "\n")[:300]
            sources.append(
                {
                    "id": index,
                    "file_name": meta.get("file_name") or meta.get("source") or "unknown",
                    "page": page,
                    "score": round(float(getattr(node, "score", 0.0) or 0.0), 3),
                    "snippet": snippet,
                }
            )
        return sources

    def _rerank(self, query: str, nodes: list, top_n: int) -> list:
        if not self.settings.rag_rerank_enabled:
            return nodes[:top_n]
        if self._reranker is None:
            from app.services.reranker import BgeReranker

            self._reranker = BgeReranker(self.settings.rag_rerank_model)
        return self._reranker.rerank(query, nodes, top_n=top_n)

    def _unique_by_file(self, nodes: list, top_n: int) -> list:
        from pathlib import Path
        import re

        seen: set[str] = set()
        unique: list = []
        for node in nodes:
            inner = getattr(node, "node", node)
            meta = dict(getattr(inner, "metadata", None) or {})
            name = str(meta.get("file_name") or meta.get("source") or "")
            stem = Path(name).stem.lower()
            key = re.sub(r"^[0-9a-f]{32}_", "", stem) or name
            if key in seen:
                continue
            seen.add(key)
            unique.append(node)
            if len(unique) >= top_n:
                break
        return unique or nodes[:top_n]

    def _retrieve_nodes(self, query: str) -> list:
        retriever = self._index.as_retriever(similarity_top_k=self.settings.rag_retrieve_k)
        nodes = list(retriever.retrieve(query))
        nodes = self._unique_by_file(nodes, top_n=self.settings.rag_retrieve_k)
        return self._rerank(query, nodes, top_n=self.settings.rag_similarity_top_k)

    def _generate(self, query: str, nodes: list) -> str:
        numbered = []
        for index, node in enumerate(nodes, start=1):
            inner = getattr(node, "node", node)
            meta = dict(getattr(inner, "metadata", None) or {})
            name = meta.get("file_name") or meta.get("source") or "unknown"
            numbered.append(f"[{index}] ({name})\n{self._node_text(node)[:1500]}")
        completion = self.llm.chat.completions.create(
            model=self.settings.openai.default_model,
            messages=[
                {"role": "system", "content": CITE_PROMPT},
                {
                    "role": "user",
                    "content": "Контекст:\n" + "\n\n".join(numbered) + f"\n\nВопрос: {query}",
                },
            ],
        )
        return (completion.choices[0].message.content or REFUSAL).strip()

    def _generate_live(self, query: str, sources: list[OfficialSource]) -> str:
        numbered = [
            f"[{index}] {source.title}\nURL: {source.url}\n{source.text}"
            for index, source in enumerate(sources, start=1)
        ]
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        completion = self.llm.chat.completions.create(
            model=self.settings.openai.default_model,
            messages=[
                {"role": "system", "content": LIVE_CITE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Текущая дата по Москве: {now:%d.%m.%Y}, {now:%A}.\n\n"
                        "Свежий контекст официального сайта:\n"
                        + "\n\n".join(numbered)
                        + f"\n\nВопрос: {query}"
                    ),
                },
            ],
        )
        return (completion.choices[0].message.content or REFUSAL).strip()

    def _format_live_sources(self, sources: list[OfficialSource]) -> list[dict]:
        return [
            {
                "id": index,
                "file_name": source.url,
                "page": None,
                "score": 1.0,
                "snippet": source.text[:300],
            }
            for index, source in enumerate(sources, start=1)
        ]

    def answer(self, question: str, history: list[dict] | None = None) -> dict:
        if self._index is None:
            self.build()
        query = self._condense(question, history)
        if self.official_site is not None and self.official_site.should_use(query):
            try:
                live_sources = self.official_site.search(query)
                if live_sources:
                    logger.info(
                        "official_site_answer",
                        query=query[:160],
                        urls=[source.url for source in live_sources],
                    )
                    exact_answer = self.official_site.exact_schedule_answer(query, live_sources)
                    return {
                        "answer": exact_answer or self._generate_live(query, live_sources),
                        "top_score": 1.0,
                        "confident": True,
                        "sources": self._format_live_sources(live_sources),
                    }
            except Exception as exc:
                logger.warning("official_site_fallback", error=str(exc), query=query[:160])
        nodes = self._retrieve_nodes(query)
        sources = self._format_sources(nodes)
        top_score = max((item["score"] for item in sources), default=0.0)
        confident = top_score >= self.settings.rag_score_threshold
        if not confident:
            logger.info("rag_score_guard", top_score=top_score, threshold=self.settings.rag_score_threshold)
            return {
                "answer": REFUSAL,
                "top_score": top_score,
                "confident": False,
                "sources": sources,
            }
        return {
            "answer": self._generate(query, nodes),
            "top_score": top_score,
            "confident": True,
            "sources": sources,
        }

    def _node_text(self, node) -> str:
        inner = getattr(node, "node", node)
        raw = ""
        if hasattr(node, "get_content"):
            raw = node.get_content() or ""
        elif hasattr(inner, "get_content"):
            raw = inner.get_content() or ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return str(raw).replace("\r\n", "\n")

    def evaluate_inputs(self, question: str) -> dict:
        """Один retrieve: полный текст чанков + ответ. Для RAGAS, не для /rag/query."""
        import time

        if self._index is None:
            self.build()
        started = time.perf_counter()
        nodes = self._retrieve_nodes(question)
        sources = self._format_sources(nodes)
        contexts = [self._node_text(node) for node in nodes]
        top_score = max((item["score"] for item in sources), default=0.0)
        confident = top_score >= self.settings.rag_score_threshold
        if not confident:
            logger.info("rag_score_guard", top_score=top_score, threshold=self.settings.rag_score_threshold)
            answer = REFUSAL
        else:
            answer = self._generate(question, nodes)
        return {
            "answer": answer,
            "retrieved_contexts": contexts,
            "top_score": top_score,
            "confident": confident,
            "sources": sources,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    def close(self) -> None:
        if self._qdrant is not None:
            self._qdrant.close()
            self._qdrant = None
        self._http.close()


def main() -> None:
    service = RAGService()
    try:
        service.build()
        result = service.answer("Какой телефон визит-центра Казанского Кремля?")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        service.close()


if __name__ == "__main__":
    main()
