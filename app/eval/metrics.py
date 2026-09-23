"""Судья RAGAS 0.4: collections-метрики + has_citation."""

from __future__ import annotations

import re
from typing import Any

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from ragas.llms import llm_factory
from ragas.metrics import discrete_metric
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

from app.core.config import Settings, get_settings

CITATION_RE = re.compile(r"\[\d+\]|\.md\b|\.pdf\b|согласно\s", re.IGNORECASE)


class CitationVerdict(BaseModel):
    label: str = Field(description="yes или no")
    reason: str = ""


def make_async_openai(settings: Settings | None = None) -> AsyncOpenAI:
    settings = settings or get_settings()
    proxy = settings.http_proxy
    http = (
        httpx.AsyncClient(proxy=proxy, trust_env=False, timeout=90.0)
        if proxy
        else httpx.AsyncClient(trust_env=False, timeout=90.0)
    )
    return AsyncOpenAI(
        api_key=settings.openai.api_key.get_secret_value(),
        base_url=settings.openai.base_url,
        http_client=http,
        timeout=90.0,
        max_retries=settings.openai.max_retries,
    )


def build_judge(settings: Settings | None = None, client: AsyncOpenAI | None = None):
    settings = settings or get_settings()
    client = client or make_async_openai(settings)
    return llm_factory(settings.eval_judge_model, client=client)


def build_embeddings(settings: Settings | None = None, client: AsyncOpenAI | None = None):
    settings = settings or get_settings()
    client = client or make_async_openai(settings)
    try:
        from ragas.embeddings.base import embedding_factory

        return embedding_factory("openai", model=settings.eval_embed_model, client=client)
    except Exception:
        from ragas.embeddings import OpenAIEmbeddings

        return OpenAIEmbeddings(client=client, model=settings.eval_embed_model)


def make_has_citation(llm) -> Any:
    @discrete_metric(name="has_citation", allowed_values=["yes", "no"])
    async def has_citation(response: str) -> str:
        prompt = (
            "Содержит ли ответ ссылку на источник: маркер вида '[1]'/'[doc_id]', "
            "имя файла, или фразу 'согласно …'. Верни label yes или no.\n\n"
            f"Ответ ассистента:\n{response}"
        )
        try:
            verdict = await llm.agenerate(prompt, CitationVerdict)
            label = (verdict.label or "").strip().lower()
            if label.startswith("yes") or label in {"да", "1", "true"}:
                return "yes"
            if label.startswith("no") or label in {"нет", "0", "false"}:
                return "no"
        except Exception:
            pass
        return "yes" if CITATION_RE.search(response or "") else "no"

    return has_citation


def build_metrics(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    client = make_async_openai(settings)
    llm = build_judge(settings, client)
    embeddings = build_embeddings(settings, client)
    return {
        "client": client,
        "faithfulness": Faithfulness(llm=llm),
        "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
        "context_precision": ContextPrecision(llm=llm),
        "context_recall": ContextRecall(llm=llm),
        "has_citation": make_has_citation(llm),
    }


def _value(result: Any) -> float | str | None:
    if result is None:
        return None
    if hasattr(result, "value"):
        return result.value
    return result


async def eval_row(
    metrics: dict[str, Any],
    *,
    user_input: str,
    response: str,
    retrieved_contexts: list[str],
    reference: str,
) -> dict[str, Any]:
    contexts = retrieved_contexts or [""]
    faith = await metrics["faithfulness"].ascore(
        user_input=user_input, response=response, retrieved_contexts=contexts
    )
    relevancy = await metrics["answer_relevancy"].ascore(user_input=user_input, response=response)
    precision = await metrics["context_precision"].ascore(
        user_input=user_input, retrieved_contexts=contexts, reference=reference
    )
    recall = await metrics["context_recall"].ascore(
        user_input=user_input, retrieved_contexts=contexts, reference=reference
    )
    citation = await metrics["has_citation"].ascore(response=response)
    cite_raw = _value(citation)
    if isinstance(cite_raw, str):
        cite_score = 1.0 if str(cite_raw).lower() in {"yes", "1", "true"} else 0.0
    else:
        cite_score = float(cite_raw or 0.0)
    return {
        "faithfulness": float(_value(faith) or 0.0),
        "answer_relevancy": float(_value(relevancy) or 0.0),
        "context_precision": float(_value(precision) or 0.0),
        "context_recall": float(_value(recall) or 0.0),
        "has_citation": cite_score,
    }
