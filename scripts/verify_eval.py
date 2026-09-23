"""Проверка, что eval/tracing-зависимости импортируются."""

from __future__ import annotations


def main() -> None:
    import pandas  # noqa: F401
    import phoenix  # noqa: F401
    import ragas
    from ragas.llms import llm_factory
    from ragas.metrics import discrete_metric
    from ragas.metrics.collections import (
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        Faithfulness,
    )

    print("ragas", ragas.__version__)
    print("llm_factory", llm_factory)
    print("metrics", Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall)
    print("discrete_metric", discrete_metric)
    try:
        from ragas.embeddings.base import embedding_factory

        print("embedding_factory", embedding_factory)
    except ImportError:
        from ragas.embeddings import OpenAIEmbeddings

        print("OpenAIEmbeddings", OpenAIEmbeddings)
    from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

    print("LlamaIndexInstrumentor", LlamaIndexInstrumentor)
    print("ok")


if __name__ == "__main__":
    main()
