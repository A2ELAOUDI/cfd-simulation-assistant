"""Index the CFD knowledge base into a FAISS vector store.

Run once (or when knowledge_base/ changes):
    python -m app.rag.indexer

Supports two embedding backends:
  - "huggingface": uses sentence-transformers (no API key needed, default)
  - "openai": uses text-embedding-3-small (requires OPENAI_API_KEY)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KNOWLEDGE_BASE_PATH = Path(os.getenv("KNOWLEDGE_BASE_PATH", str(REPO_ROOT / "knowledge_base")))
FAISS_INDEX_PATH = Path(os.getenv("FAISS_INDEX_PATH", str(REPO_ROOT / "faiss_index")))
EMBEDDINGS_BACKEND = os.getenv("EMBEDDINGS_BACKEND", "huggingface")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 120


def _get_embeddings():
    """Return the configured embedding model."""
    if EMBEDDINGS_BACKEND == "openai":
        try:
            from langchain_openai import OpenAIEmbeddings
            return OpenAIEmbeddings(model="text-embedding-3-small")
        except Exception as exc:
            log.warning("OpenAI embeddings unavailable (%s) — falling back to HuggingFace", exc)

    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"},
        )
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers not installed. "
            "Run: pip install sentence-transformers"
        ) from exc


def _load_documents():
    """Load all Markdown files from the knowledge base directory."""
    from langchain_community.document_loaders import TextLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    if not KNOWLEDGE_BASE_PATH.exists():
        raise FileNotFoundError(f"Knowledge base not found: {KNOWLEDGE_BASE_PATH}")

    md_files = list(KNOWLEDGE_BASE_PATH.rglob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No .md files found in {KNOWLEDGE_BASE_PATH}")

    log.info("Found %d Markdown files in %s", len(md_files), KNOWLEDGE_BASE_PATH)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " "],
    )

    all_docs = []
    for md_path in sorted(md_files):
        try:
            loader = TextLoader(str(md_path), encoding="utf-8")
            raw_docs = loader.load()
            chunks = splitter.split_documents(raw_docs)
            # Enrich metadata
            for chunk in chunks:
                chunk.metadata["source_file"] = md_path.name
                chunk.metadata["category"] = md_path.parent.name
            all_docs.extend(chunks)
            log.info("  Loaded %s → %d chunks", md_path.name, len(chunks))
        except Exception as exc:
            log.warning("Could not load %s: %s", md_path, exc)

    log.info("Total: %d chunks from %d files", len(all_docs), len(md_files))
    return all_docs


def build_index(force: bool = False) -> None:
    """Build the FAISS index from the knowledge base.

    Parameters
    ----------
    force:
        If True, rebuild even if index already exists.
    """
    if FAISS_INDEX_PATH.exists() and not force:
        log.info("Index already exists at %s. Use --force to rebuild.", FAISS_INDEX_PATH)
        return

    from langchain_community.vectorstores import FAISS

    docs = _load_documents()
    embeddings = _get_embeddings()

    log.info("Building FAISS index with %d chunks ...", len(docs))
    vectorstore = FAISS.from_documents(docs, embeddings)

    FAISS_INDEX_PATH.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(FAISS_INDEX_PATH))
    log.info("Index saved → %s", FAISS_INDEX_PATH)


def load_index():
    """Load the FAISS index from disk.

    Returns
    -------
    FAISS vectorstore instance, or None if index doesn't exist.
    """
    from langchain_community.vectorstores import FAISS

    if not FAISS_INDEX_PATH.exists():
        log.warning(
            "No FAISS index found at %s. Run `python -m app.rag.indexer` first.",
            FAISS_INDEX_PATH,
        )
        return None

    embeddings = _get_embeddings()
    try:
        return FAISS.load_local(
            str(FAISS_INDEX_PATH),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    except Exception as exc:
        log.error("Failed to load FAISS index: %s", exc)
        return None


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Build the CFD knowledge base FAISS index.")
    p.add_argument("--force", action="store_true", help="Rebuild even if index exists")
    args = p.parse_args()
    build_index(force=args.force)
