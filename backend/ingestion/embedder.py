"""
BkAI Embedding & Ingestion Pipeline.

Supports ChromaDB and BM25 indexing.
"""

from __future__ import annotations

import hashlib
import pickle
import uuid
from pathlib import Path

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer

from config.settings import get_settings
from ingestion.chunker import Chunk
from utils.logger import get_logger
from utils.vietnamese import tokenize_vi

logger = get_logger(__name__)

_embedding_model: SentenceTransformer | None = None
_bge_model = None
_chroma_client: chromadb.ClientAPI | None = None


def _use_bge_m3() -> bool:
    return "bge-m3" in get_settings().embedding.model.lower()


def get_bge_model():
    global _bge_model
    if _bge_model is None:
        from FlagEmbedding import BGEM3FlagModel
        settings = get_settings()
        logger.info("loading_bge_m3", model=settings.embedding.model)
        _bge_model = BGEM3FlagModel(settings.embedding.model, use_fp16=False)
        logger.info("bge_m3_loaded")
    return _bge_model


def get_embedding_model() -> SentenceTransformer:
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
            dim=_embedding_model.get_sentence_embedding_dimension(),
        )
    return _embedding_model


def get_embedding_dimension() -> int:
    if _use_bge_m3():
        return 1024
    return get_embedding_model().get_sentence_embedding_dimension()


def get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        settings = get_settings()
        persist_dir = Path(settings.chroma.persist_dir)
        persist_dir.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(persist_dir))
    return _chroma_client



def encode_texts(texts: list[str]) -> tuple[list[list[float]], list[dict[int, float]]]:
    if _use_bge_m3():
        model = get_bge_model()
        output = model.encode(
            texts,
            batch_size=get_settings().embedding.batch_size,
            max_length=8192,
            return_dense=True,
            return_sparse=True,
        )
        dense = [vec.tolist() if hasattr(vec, "tolist") else list(vec) for vec in output["dense_vecs"]]
        sparse = []
        for lex_weights in output["lexical_weights"]:
            sparse.append({int(k): float(v) for k, v in lex_weights.items()})
        return dense, sparse

    model = get_embedding_model()
    dense = model.encode(texts, normalize_embeddings=True, show_progress_bar=True).tolist()
    return dense, [{} for _ in texts]


def encode_query(query: str, return_sparse: bool = True) -> tuple[list[float], dict[int, float]]:
    dense_list, sparse_list = encode_texts([query])
    sparse = sparse_list[0] if return_sparse else {}
    return dense_list[0], sparse


def _make_chunk_id(chunk: Chunk) -> str:
    content_hash = hashlib.md5(chunk.content.encode("utf-8")).hexdigest()[:12]
    source = chunk.metadata.get("source_file", "unknown")
    idx = chunk.metadata.get("chunk_index", chunk.chunk_index)
    return f"{source}_{idx}_{content_hash}"


def embed_chunks(chunks: list[Chunk], batch_size: int | None = None) -> list[list[float]]:
    settings = get_settings()
    batch = batch_size or settings.embedding.batch_size
    texts = [c.content for c in chunks]
    logger.info("embedding_start", total_chunks=len(texts), model=settings.embedding.model)
    dense, _ = encode_texts(texts)
    logger.info("embedding_complete", total_chunks=len(texts), dim=len(dense[0]))
    return dense



def ingest_to_chromadb(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    collection_name: str | None = None,
) -> int:
    settings = get_settings()
    client = get_chroma_client()
    col_name = collection_name or settings.chroma.collection_name
    try:
        client.delete_collection(col_name)
        logger.info("chromadb_stale_collection_deleted", collection=col_name)
    except Exception:
        pass
    collection = client.get_or_create_collection(
        name=col_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids, documents, metadatas, embeds = [], [], [], []
    for chunk, embedding in zip(chunks, embeddings):
        ids.append(_make_chunk_id(chunk))
        documents.append(chunk.content)
        metadatas.append(chunk.metadata)
        embeds.append(embedding)

    total = 0
    batch_size = 5000
    for i in range(0, len(ids), batch_size):
        end = min(i + batch_size, len(ids))
        collection.upsert(
            ids=ids[i:end],
            documents=documents[i:end],
            metadatas=metadatas[i:end],
            embeddings=embeds[i:end],
        )
        total += end - i

    logger.info("chromadb_ingestion_complete", collection=col_name, chunks=total)
    return total


def build_bm25_index(chunks: list[Chunk]) -> Path:
    from rank_bm25 import BM25Okapi

    settings = get_settings()
    output_dir = settings.processed_data_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenized_corpus = [tokenize_vi(chunk.content) for chunk in chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    bm25_path = output_dir / "bm25_index.pkl"
    with open(bm25_path, "wb") as f:
        pickle.dump(bm25, f)

    chunks_path = output_dir / "bm25_chunks.pkl"
    chunk_data = [{"content": c.content, "metadata": c.metadata} for c in chunks]
    with open(chunks_path, "wb") as f:
        pickle.dump(chunk_data, f)

    return bm25_path
