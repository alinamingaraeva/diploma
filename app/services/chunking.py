"""Три стратегии нарезки для эксперимента 5.4."""

from __future__ import annotations

import re
from typing import Literal

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import (
    SemanticSplitterNodeParser,
    SentenceSplitter,
    TokenTextSplitter,
)
from llama_index.core.node_parser.interface import NodeParser

ChunkStrategy = Literal["fixed", "recursive", "semantic"]

_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


def split_russian_sentences(text: str) -> list[str]:
    """Токенизатор предложений с учётом русской пунктуации."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = _SENTENCE_RE.split(cleaned)
    return [part.strip() for part in parts if part.strip()]


def make_fixed_splitter(chunk_size: int = 512, chunk_overlap: int = 64) -> TokenTextSplitter:
    return TokenTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def make_recursive_splitter(chunk_size: int = 512, chunk_overlap: int = 64) -> SentenceSplitter:
    return SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        paragraph_separator="\n\n",
        chunking_tokenizer_fn=split_russian_sentences,
    )


def make_semantic_splitter(embed_model: BaseEmbedding) -> SemanticSplitterNodeParser:
    return SemanticSplitterNodeParser(
        buffer_size=1,
        breakpoint_percentile_threshold=95,
        embed_model=embed_model,
        sentence_splitter=split_russian_sentences,
    )


def get_splitter(
    strategy: ChunkStrategy,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    embed_model: BaseEmbedding | None = None,
) -> NodeParser:
    if strategy == "fixed":
        return make_fixed_splitter(chunk_size, chunk_overlap)
    if strategy == "recursive":
        return make_recursive_splitter(chunk_size, chunk_overlap)
    if strategy == "semantic":
        if embed_model is None:
            raise ValueError("semantic splitter нужен embed_model")
        return make_semantic_splitter(embed_model)
    raise ValueError(f"Неизвестная стратегия chunking: {strategy}")
