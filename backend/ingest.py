#!/usr/bin/env python3
"""
BKAi Data Ingestion CLI.

Runs the complete ingestion pipeline:
  1. Load raw documents (MD + CSV)
  2. Enrich with metadata tags
  3. Chunk into retrieval-ready segments
  4. Embed with sentence-transformers
  5. Persist to ChromaDB (vector) + BM25 (lexical)

Usage:
    python ingest.py
    python ingest.py --collection bkai_v2
"""

from __future__ import annotations

import argparse
import sys
import time

from utils.logger import setup_logging, get_logger

# Initialize logging before any other imports
setup_logging(log_level="INFO")
logger = get_logger("ingest")


def run_ingestion(collection_name: str | None = None) -> None:
    """Execute the full ingestion pipeline."""
    t0 = time.time()

    # ── Step 1: Load documents ──
    logger.info("step_1_load_documents")
    from ingestion.loader import load_all_documents

    documents = load_all_documents()
    logger.info("step_1_complete", total_docs=len(documents))

    if not documents:
        logger.error("no_documents_found")
        sys.exit(1)

    # ── Step 2: Enrich metadata ──
    logger.info("step_2_metadata_tagging")
    from ingestion.metadata_tagger import tag_all_documents

    documents = tag_all_documents(documents)
    logger.info("step_2_complete")

    # ── Step 3: Chunk documents ──
    logger.info("step_3_chunking")
    from ingestion.chunker import chunk_all_documents

    chunks = chunk_all_documents(documents)
    logger.info("step_3_complete", total_chunks=len(chunks))

    if not chunks:
        logger.error("no_chunks_produced")
        sys.exit(1)

    # ── Step 4: Generate embeddings ──
    logger.info("step_4_embedding")
    from ingestion.embedder import embed_chunks

    embeddings = embed_chunks(chunks)
    logger.info("step_4_complete", embedding_dim=len(embeddings[0]))

    # ── Step 5a: Persist to ChromaDB ──
    logger.info("step_5a_chromadb_ingestion")
    from ingestion.embedder import ingest_to_chromadb

    count = ingest_to_chromadb(chunks, embeddings, collection_name)
    logger.info("step_5a_complete", ingested=count)

    # ── Step 5b: Build BM25 index ──
    logger.info("step_5b_bm25_index")
    from ingestion.embedder import build_bm25_index

    bm25_path = build_bm25_index(chunks)
    logger.info("step_5b_complete", path=str(bm25_path))

    # ── Done ──
    elapsed = time.time() - t0
    logger.info(
        "ingestion_pipeline_complete",
        total_documents=len(documents),
        total_chunks=len(chunks),
        elapsed_seconds=round(elapsed, 2),
    )

    print(f"\n{'='*60}")
    print(f"  ✅ Ingestion Complete!")
    print(f"  📄 Documents loaded:  {len(documents)}")
    print(f"  🧩 Chunks created:    {len(chunks)}")
    print(f"  📐 Embedding dim:     {len(embeddings[0])}")
    print(f"  💾 ChromaDB count:    {count}")
    print(f"  🔍 BM25 index:        {bm25_path}")
    print(f"  ⏱  Time elapsed:      {elapsed:.1f}s")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BKAi Data Ingestion Pipeline",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="ChromaDB collection name (default: from settings)",
    )
    args = parser.parse_args()
    run_ingestion(collection_name=args.collection)


if __name__ == "__main__":
    main()
