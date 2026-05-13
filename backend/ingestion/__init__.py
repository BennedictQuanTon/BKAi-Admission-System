"""
BKAi Ingestion Package.

Provides the complete data processing pipeline:
  load → tag → chunk → embed → persist
"""

from ingestion.loader import Document, load_all_documents
from ingestion.chunker import Chunk, chunk_all_documents
from ingestion.metadata_tagger import tag_all_documents, enrich_metadata
from ingestion.embedder import (
    embed_chunks,
    ingest_to_chromadb,
    build_bm25_index,
    get_embedding_model,
    get_chroma_client,
)

__all__ = [
    "Document",
    "Chunk",
    "load_all_documents",
    "tag_all_documents",
    "chunk_all_documents",
    "embed_chunks",
    "ingest_to_chromadb",
    "build_bm25_index",
    "enrich_metadata",
    "get_embedding_model",
    "get_chroma_client",
]
