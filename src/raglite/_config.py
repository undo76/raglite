"""RAGLite config."""

import contextlib
import os
from dataclasses import dataclass, field
from functools import partial
from io import StringIO
from typing import TYPE_CHECKING

from llama_cpp import llama_supports_gpu_offload
from sqlalchemy.engine import URL

from raglite._prompts import RAG_INSTRUCTION_TEMPLATE
from raglite._rag import retrieve_rag_context
from raglite._search import (
    hybrid_search,
    keyword_search,
    rerank_chunks,
    vector_search,
)

if TYPE_CHECKING:
    from raglite._typing import ChunkSpanSearchMethod

# Suppress rerankers output on import until [1] is fixed.
# [1] https://github.com/AnswerDotAI/rerankers/issues/36
with contextlib.redirect_stdout(StringIO()):
    from rerankers.models.flashrank_ranker import FlashRankRanker
    from rerankers.models.ranker import BaseRanker


default_retrieval: "ChunkSpanSearchMethod" = partial(
    retrieve_rag_context,
    max_chunk_spans=5,
    search=partial(
        hybrid_search,
        subsearches=[
            partial(keyword_search, max_chunks=20),
            partial(vector_search, max_chunks=20),
        ],
        max_chunks=20,
    ),
    rerank=rerank_chunks,
    chunk_neighbors=(-1, 1),
)


@dataclass(frozen=True)
class RAGLiteConfig:
    """Configuration for RAGLite."""

    # Database config.
    db_url: str | URL = "sqlite:///raglite.sqlite"
    # LLM config used for generation.
    llm: str = field(
        default_factory=lambda: (
            "llama-cpp-python/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/*Q4_K_M.gguf@8192"
            if llama_supports_gpu_offload()
            else "llama-cpp-python/bartowski/Llama-3.2-3B-Instruct-GGUF/*Q4_K_M.gguf@4096"
        )
    )
    llm_max_tries: int = 4
    # Embedder config used for indexing.
    embedder: str = field(
        default_factory=lambda: (  # Nomic-embed may be better if only English is used.
            "llama-cpp-python/lm-kit/bge-m3-gguf/*F16.gguf@1024"
            if llama_supports_gpu_offload() or (os.cpu_count() or 1) >= 4  # noqa: PLR2004
            else "llama-cpp-python/lm-kit/bge-m3-gguf/*Q4_K_M.gguf@1024"
        )
    )
    embedder_normalize: bool = True
    embedder_sentence_window_size: int = 3
    # Chunk config used to partition documents into chunks.
    chunk_max_size: int = 1440  # Max number of characters per chunk.
    # Vector search config.
    vector_search_index_metric: str = "cosine"  # The query adapter supports "dot" and "cosine".
    vector_search_query_adapter: bool = True
    # Reranking config.
    reranker: BaseRanker | tuple[tuple[str, BaseRanker], ...] | None = field(
        default_factory=lambda: (
            ("en", FlashRankRanker("ms-marco-MiniLM-L-12-v2", verbose=0)),
            ("other", FlashRankRanker("ms-marco-MultiBERT-L-12", verbose=0)),
        ),
        compare=False,  # Exclude the reranker from comparison to avoid lru_cache misses.
    )
    retrieval: "ChunkSpanSearchMethod" = default_retrieval
    system_prompt: str | None = None
    rag_instruction_template: str = RAG_INSTRUCTION_TEMPLATE

    def __post_init__(self) -> None:
        # Late chunking with llama-cpp-python does not apply sentence windowing.
        if self.embedder.startswith("llama-cpp-python"):
            object.__setattr__(self, "embedder_sentence_window_size", 1)
