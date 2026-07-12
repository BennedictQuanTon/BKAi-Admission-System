#!/usr/bin/env python3
"""BkAI Data Ingestion CLI."""

from __future__ import annotations

import argparse
import sys
import time
import os

# Limit CPU threads for PyTorch, NumPy, and OpenMP to prevent high RAM/CPU spikes
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"
os.environ["OPENBLAS_NUM_THREADS"] = "4"
os.environ["VECLIB_MAXIMUM_THREADS"] = "4"
os.environ["NUMEXPR_NUM_THREADS"] = "4"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import torch
torch.set_num_threads(4)

from config.settings import get_settings
from utils.logger import setup_logging, get_logger

setup_logging(log_level="INFO")
logger = get_logger("ingest")


def run_ingestion(collection_name: str | None = None) -> None:
    t0 = time.time()
    settings = get_settings()

    from ingestion.loader import load_all_documents
    documents = load_all_documents()
    if not documents:
        logger.error("no_documents_found")
        sys.exit(1)

    from ingestion.metadata_tagger import tag_all_documents
    documents = tag_all_documents(documents)

    from ingestion.chunker import chunk_all_documents
    chunks = chunk_all_documents(documents)
    if not chunks:
        logger.error("no_chunks_produced")
        sys.exit(1)

    from ingestion.embedder import (
        build_bm25_index,
        embed_chunks,
        ingest_to_chromadb,
    )

    embeddings = embed_chunks(chunks)
    count = ingest_to_chromadb(chunks, embeddings, collection_name)
    store_label = "ChromaDB"
    embedding_dim = len(embeddings[0])

    bm25_path = build_bm25_index(chunks)
    elapsed = time.time() - t0

    # Explicit garbage collection to free memory
    import gc
    gc.collect()

    print(f"\n{'='*60}")
    print("  ✅ Ingestion Complete!")
    print(f"  📄 Documents loaded:  {len(documents)}")
    print(f"  🧩 Chunks created:    {len(chunks)}")
    print(f"  📐 Embedding dim:     {embedding_dim}")
    print(f"  💾 {store_label} count:    {count}")
    print(f"  🔍 BM25 index:        {bm25_path}")
    print(f"  ⏱  Time elapsed:      {elapsed:.1f}s")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="BkAI Data Ingestion Pipeline")
    parser.add_argument("--collection", type=str, default=None)
    args = parser.parse_args()
    run_ingestion(collection_name=args.collection)


if __name__ == "__main__":
    main()
