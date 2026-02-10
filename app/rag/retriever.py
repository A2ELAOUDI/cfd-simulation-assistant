"""RAG retrieval: search the FAISS knowledge base and format context for the LLM."""

from __future__ import annotations

import logging
from typing import Any

from app.rag.indexer import load_index

log = logging.getLogger(__name__)

_vectorstore = None  # module-level singleton


def _get_vectorstore():
    """Lazy-load the FAISS index (cached after first call)."""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = load_index()
    return _vectorstore


def search(
    query: str,
    k: int = 4,
    score_threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """Search the knowledge base for documents relevant to the query.

    Parameters
    ----------
    query:
        Natural language or technical query string.
    k:
        Maximum number of chunks to return.
    score_threshold:
        Minimum similarity score (0–1, higher = more similar).

    Returns
    -------
    list of dicts with keys: 'content', 'source', 'category', 'score'
    """
    vs = _get_vectorstore()
    if vs is None:
        log.warning("Knowledge base not loaded — returning empty results.")
        return []

    try:
        results = vs.similarity_search_with_relevance_scores(query, k=k)
    except Exception as exc:
        log.error("FAISS search failed: %s", exc)
        return []

    hits: list[dict[str, Any]] = []
    for doc, score in results:
        if score < score_threshold:
            continue
        hits.append(
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source_file", "unknown"),
                "category": doc.metadata.get("category", "unknown"),
                "score": round(float(score), 4),
            }
        )

    log.debug("Retrieved %d/%d chunks for query: %r", len(hits), k, query[:80])
    return hits


def format_context(hits: list[dict[str, Any]], max_chars: int = 3000) -> str:
    """Format retrieved chunks into a context string for the LLM prompt.

    Parameters
    ----------
    hits:
        Results from search().
    max_chars:
        Truncate the total context to this length.

    Returns
    -------
    A formatted string with source attribution for each chunk.
    """
    if not hits:
        return "No relevant documentation found in the knowledge base."

    parts: list[str] = []
    total_len = 0
    for hit in hits:
        section = (
            f"[Source: {hit['source']} | Category: {hit['category']} "
            f"| Relevance: {hit['score']:.2f}]\n{hit['content']}"
        )
        if total_len + len(section) > max_chars:
            break
        parts.append(section)
        total_len += len(section)

    return "\n\n---\n\n".join(parts)


def retrieve_and_format(query: str, k: int = 4) -> str:
    """One-call convenience: search + format."""
    hits = search(query, k=k)
    return format_context(hits)
