"""RAG module: indexing and retrieval for the CFD knowledge base."""

from app.rag.retriever import retrieve_and_format, search

__all__ = ["search", "retrieve_and_format"]
