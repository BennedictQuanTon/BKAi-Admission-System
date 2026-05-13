"""
BKAi Embedding & Ingestion Pipeline.

Embeds document chunks and persists them to ChromaDB vector store
and builds a parallel BM25 lexical index.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from config.settings import get_settings
from ingestion.chunker import Chunk
from utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# Singleton holders
# ──────────────────────────────────────────────
_embedding_model: SentenceTransformer | None = None
_chroma_client: chromadb.ClientAPI | None = None


def get_embedding_model() -> SentenceTransformer:
    """Get or initialize the embedding model (singleton)."""
    global _embedding_model
    if _embedding_model is None:
        settings = get_settings()
        logger.info("loading_embedding_model", model=settings.embedding.model)
        _embedding_model = SentenceTransformer(
            settings.embedding.model,
            device=settings.embedding.device,
        )
        logger.info(
            "embedding_model_loaded",
            model=settings.embedding.model,
            dim=_embedding_model.get_embedding_dimension(),
        )
    return _embedding_model


def get_chroma_client() -> chromadb.ClientAPI:
    """Get or initialize the ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        settings = get_settings()
        persist_dir = Path(settings.chroma.persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(persist_dir))
        logger.info("chromadb_initialized", path=str(persist_dir))
    return _chroma_client


def _make_chunk_id(chunk: Chunk) -> str:
    """Generate a deterministic ID for a chunk based on content hash."""
    content_hash = hashlib.md5(chunk.content.encode("utf-8")).hexdigest()[:12]
    source = chunk.metadata.get("source_file", "unknown")
    idx = chunk.metadata.get("chunk_index", chunk.chunk_index)
    return f"{source}_{idx}_{content_hash}"


def embed_chunks(chunks: list[Chunk], batch_size: int = 64) -> list[list[float]]:
    """
    Generate embeddings for all chunks.

    Args:
        chunks: List of text chunks to embed.
        batch_size: Number of chunks to embed at once.

    Returns:
        List of embedding vectors.
    """
    model = get_embedding_model()
    texts = [c.content for c in chunks]

    logger.info("embedding_start", total_chunks=len(texts), batch_size=batch_size)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    logger.info("embedding_complete", total_chunks=len(texts))
    return embeddings.tolist()


def ingest_to_chromadb(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    collection_name: str | None = None,
) -> int:
    """
    Persist chunks + embeddings to ChromaDB.

    Args:
        chunks: Document chunks with metadata.
        embeddings: Pre-computed embedding vectors.
        collection_name: Override collection name (default from settings).

    Returns:
        Number of chunks ingested.
    """
    settings = get_settings()
    client = get_chroma_client()
    col_name = collection_name or settings.chroma.collection_name

    # Get or create collection
    collection = client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"},
    )

    # Prepare data for upsert
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []
    embeds: list[list[float]] = []

    for chunk, embedding in zip(chunks, embeddings):
        chunk_id = _make_chunk_id(chunk)
        ids.append(chunk_id)
        documents.append(chunk.content)
        metadatas.append(chunk.metadata)
        embeds.append(embedding)

    # Batch upsert (ChromaDB max batch = 5461)
    batch_size = 5000
    total = 0
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        collection.upsert(
            ids=ids[i:end],
            documents=documents[i:end],
            metadatas=metadatas[i:end],
            embeddings=embeds[i:end],
        )
        total += end - i

    logger.info(
        "chromadb_ingestion_complete",
        collection=col_name,
        chunks_ingested=total,
        collection_count=collection.count(),
    )
    return total


def build_bm25_index(chunks: list[Chunk]) -> Path:
    """
    Build and persist a BM25 lexical index for hybrid search.

    Saves the index and chunk data to disk as pickle files
    in the processed data directory.

    Args:
        chunks: List of document chunks.

    Returns:
        Path to the saved BM25 index.
    """
    from rank_bm25 import BM25Okapi

    settings = get_settings()
    output_dir = settings.processed_data_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Tokenize: simple whitespace + lowercasing for Vietnamese
    tokenized_corpus = []
    for chunk in chunks:
        tokens = chunk.content.lower().split()
        tokenized_corpus.append(tokens)

    bm25 = BM25Okapi(tokenized_corpus)

    # Save BM25 index
    bm25_path = output_dir / "bm25_index.pkl"
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f)

    # Save chunk metadata alongside (for result lookup)
    chunks_path = output_dir / "bm25_chunks.pkl"
    chunk_data = [
        {"content": c.content, "metadata": c.metadata}
        for c in chunks
    ]
    with open(chunks_path, "wb") as f:
        pickle.dump(chunk_data, f)

    logger.info(
        "bm25_index_built",
        total_chunks=len(chunks),
        index_path=str(bm25_path),
    )
    return bm25_path
