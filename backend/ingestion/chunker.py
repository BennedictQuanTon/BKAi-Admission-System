"""
BKAi Semantic Chunker.

Splits documents into retrieval-optimized chunks using
section-aware, metadata-preserving chunking strategy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingestion.loader import Document
from utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
MAX_CHUNK_CHARS = 1500       # ~375 tokens (avg 4 chars/token)
OVERLAP_CHARS = 200          # Overlap between consecutive chunks
MIN_CHUNK_CHARS = 100        # Skip chunks smaller than this
TABLE_ROW_PATTERN = re.compile(r"^\s*\|.+\|", re.MULTILINE)


@dataclass
class Chunk:
    """A retrieval-ready text chunk with inherited metadata."""

    content: str
    metadata: dict[str, str] = field(default_factory=dict)
    chunk_index: int = 0


def chunk_document(doc: Document) -> list[Chunk]:
    """
    Split a document into retrieval-optimized chunks.

    Strategy:
    - CSV rows: Keep as single chunk (already row-level).
    - Markdown with tables: Keep tables together.
    - Long sections: Split at paragraph boundaries with overlap.
    """
    if doc.doc_type == "csv_row":
        return _chunk_csv_row(doc)

    return _chunk_markdown_section(doc)


def _chunk_csv_row(doc: Document) -> list[Chunk]:
    """CSV rows are already atomic — one chunk per row."""
    if len(doc.content.strip()) < MIN_CHUNK_CHARS:
        return []

    return [Chunk(
        content=doc.content,
        metadata={**doc.metadata, "chunk_type": "csv_row"},
        chunk_index=0,
    )]


def _chunk_markdown_section(doc: Document) -> list[Chunk]:
    """
    Chunk a markdown section using semantic boundaries.

    Priority order for split points:
    1. ### sub-headers
    2. Paragraph breaks (double newline)
    3. Single newlines (last resort)

    Tables are never split mid-row.
    """
    text = doc.content
    if len(text) <= MAX_CHUNK_CHARS:
        # Short enough to be a single chunk
        if len(text.strip()) < MIN_CHUNK_CHARS:
            return []
        return [Chunk(
            content=text,
            metadata={**doc.metadata, "chunk_type": "full_section"},
            chunk_index=0,
        )]

    # Identify table blocks and protect them
    blocks = _split_into_blocks(text)
    chunks: list[Chunk] = []
    current_text = ""
    chunk_idx = 0

    for block in blocks:
        # If adding this block exceeds limit, flush current chunk
        if current_text and len(current_text) + len(block) > MAX_CHUNK_CHARS:
            chunks.append(Chunk(
                content=current_text.strip(),
                metadata={**doc.metadata, "chunk_type": "split_section"},
                chunk_index=chunk_idx,
            ))
            chunk_idx += 1

            # Overlap: carry over end of previous chunk
            overlap_start = max(0, len(current_text) - OVERLAP_CHARS)
            current_text = current_text[overlap_start:]

        current_text += block + "\n"

        # If a single block exceeds the limit (e.g., big table),
        # force-flush it as its own chunk
        if len(current_text) > MAX_CHUNK_CHARS * 1.5:
            chunks.append(Chunk(
                content=current_text.strip(),
                metadata={**doc.metadata, "chunk_type": "large_block"},
                chunk_index=chunk_idx,
            ))
            chunk_idx += 1
            current_text = ""

    # Flush remaining
    if current_text.strip() and len(current_text.strip()) >= MIN_CHUNK_CHARS:
        chunks.append(Chunk(
            content=current_text.strip(),
            metadata={**doc.metadata, "chunk_type": "split_section"},
            chunk_index=chunk_idx,
        ))

    return chunks


def _split_into_blocks(text: str) -> list[str]:
    """
    Split text into semantic blocks, keeping tables intact.

    Returns a list of blocks where each block is either:
    - A complete table (all rows together)
    - A paragraph or sub-section
    """
    lines = text.split("\n")
    blocks: list[str] = []
    current_block: list[str] = []
    in_table = False

    for line in lines:
        is_table_line = bool(TABLE_ROW_PATTERN.match(line))

        if is_table_line:
            if not in_table and current_block:
                # Flush non-table block before table starts
                blocks.append("\n".join(current_block))
                current_block = []
            in_table = True
            current_block.append(line)
        else:
            if in_table:
                # Table just ended, flush table block
                blocks.append("\n".join(current_block))
                current_block = []
                in_table = False

            # Check for paragraph break
            if not line.strip():
                if current_block:
                    blocks.append("\n".join(current_block))
                    current_block = []
            else:
                current_block.append(line)

    # Flush remaining
    if current_block:
        blocks.append("\n".join(current_block))

    return [b for b in blocks if b.strip()]


def chunk_all_documents(documents: list[Document]) -> list[Chunk]:
    """
    Chunk all documents and return a flat list of chunks.

    Args:
        documents: List of Document objects to chunk.

    Returns:
        Flat list of Chunk objects ready for embedding.
    """
    all_chunks: list[Chunk] = []

    for doc in documents:
        chunks = chunk_document(doc)
        all_chunks.extend(chunks)

    logger.info(
        "chunking_complete",
        input_docs=len(documents),
        output_chunks=len(all_chunks),
        avg_chunk_size=int(
            sum(len(c.content) for c in all_chunks) / max(len(all_chunks), 1)
        ),
    )
    return all_chunks
