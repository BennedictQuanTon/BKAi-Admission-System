"""
BKAi Document Loader.

Loads raw markdown and CSV files from the data directory,
extracting metadata and preparing for the chunking pipeline.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import get_settings
from utils.logger import get_logger
from utils.text_cleaning import normalize_unicode

logger = get_logger(__name__)


@dataclass
class Document:
    """
    Represents a loaded document with content and metadata.

    Attributes:
        content: The full text content of the document.
        metadata: Key-value metadata extracted from the document.
        source_file: Original filename.
        doc_type: Type of document (markdown, csv, table).
    """

    content: str
    metadata: dict[str, str] = field(default_factory=dict)
    source_file: str = ""
    doc_type: str = "markdown"


def load_markdown_file(filepath: Path) -> list[Document]:
    """
    Load a markdown file and split it into section-level documents.

    Each ## header creates a new document, preserving the section
    hierarchy and attaching metadata about position and source.

    Args:
        filepath: Path to the markdown file.

    Returns:
        List of Document objects, one per section.
    """
    text = filepath.read_text(encoding="utf-8")
    text = normalize_unicode(text)
    filename = filepath.name

    # Split by ## headers (level 2)
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    documents: list[Document] = []

    for idx, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # Extract section title
        title_match = re.match(r"^##\s+(.+?)(?:\n|$)", section)
        section_title = title_match.group(1).strip() if title_match else f"Section {idx}"

        # Detect category from section content
        category = _detect_category(section_title, section)

        doc = Document(
            content=section,
            metadata={
                "source_file": filename,
                "section_index": str(idx),
                "section_title": section_title,
                "category": category,
                "doc_type": "markdown",
            },
            source_file=filename,
            doc_type="markdown",
        )
        documents.append(doc)

    logger.info(
        "markdown_loaded",
        file=filename,
        sections=len(documents),
    )
    return documents


def load_csv_file(filepath: Path) -> list[Document]:
    """
    Load a CSV file and convert each row into a document.

    Each row becomes a structured text document with column headers
    as context, optimized for retrieval.

    Args:
        filepath: Path to the CSV file.

    Returns:
        List of Document objects, one per row.
    """
    filename = filepath.name
    documents: list[Document] = []

    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        for row_idx, row in enumerate(reader):
            # Build structured text from row
            parts: list[str] = []
            for header in headers:
                value = normalize_unicode(row.get(header, "").strip())
                if value and value != "-":
                    # Strip markdown bold from CSV values
                    clean_val = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
                    clean_val = re.sub(r"_(.+?)_", r"\1", clean_val)
                    parts.append(f"{header}: {clean_val}")

            content = "\n".join(parts)
            if not content.strip():
                continue

            # Extract major name for metadata
            major_name = row.get("Tên ngành", "")
            major_name = re.sub(r"\*\*(.+?)\*\*", r"\1", major_name)
            major_name = re.sub(r"_(.+?)_", r"\1", major_name).strip()

            # Detect program type from filename
            program_type = _detect_program_type(filename)

            doc = Document(
                content=content,
                metadata={
                    "source_file": filename,
                    "row_index": str(row_idx),
                    "category": "nganh_diem_chuan",
                    "program_type": program_type,
                    "major_name": major_name,
                    "major_code": row.get("Mã", ""),
                    "doc_type": "csv_row",
                },
                source_file=filename,
                doc_type="csv_row",
            )
            documents.append(doc)

    logger.info(
        "csv_loaded",
        file=filename,
        rows=len(documents),
    )
    return documents


def load_all_documents() -> list[Document]:
    """
    Load all documents from raw/ and csv/ directories.

    Returns:
        Combined list of all Document objects from all data sources.
    """
    settings = get_settings()
    all_docs: list[Document] = []

    # Load markdown files
    raw_dir = settings.raw_data_dir
    if raw_dir.exists():
        for md_file in sorted(raw_dir.glob("*.md")):
            docs = load_markdown_file(md_file)
            all_docs.extend(docs)

    # Load CSV files
    csv_dir = settings.csv_data_dir
    if csv_dir.exists():
        for csv_file in sorted(csv_dir.glob("*.csv")):
            docs = load_csv_file(csv_file)
            all_docs.extend(docs)

    logger.info(
        "all_documents_loaded",
        total_documents=len(all_docs),
        markdown_count=sum(1 for d in all_docs if d.doc_type == "markdown"),
        csv_count=sum(1 for d in all_docs if d.doc_type == "csv_row"),
    )
    return all_docs


# ──────────────────────────────────────────────
# Private helpers
# ──────────────────────────────────────────────

_CATEGORY_KEYWORDS = {
    "gioi_thieu": ["giới thiệu", "lịch sử", "sứ mạng", "tầm nhìn", "danh hiệu"],
    "nganh_hoc": ["ngành", "khoa", "chuyên ngành", "đào tạo", "chương trình"],
    "tuyen_sinh": ["tuyển sinh", "xét tuyển", "phương thức", "đối tượng", "điểm chuẩn", "công thức"],
    "nganh_diem_chuan": ["mã ngành", "chỉ tiêu", "điểm xét tuyển", "tổ hợp"],
    "hoc_phi": ["học phí", "tài chính", "miễn giảm", "hỗ trợ", "vay"],
    "hoc_bong": ["học bổng", "tài trợ", "du học", "trao đổi"],
    "hoat_dong": ["sinh viên", "thể thao", "khởi nghiệp", "cuộc thi", "sự kiện"],
    "co_so": ["cơ sở", "ký túc xá", "địa chỉ", "liên hệ"],
    "kiem_dinh": ["kiểm định", "chất lượng", "abet", "aun-qa", "iso"],
    "nghien_cuu": ["nghiên cứu", "khoa học", "hợp tác", "công nghệ"],
}


def _detect_category(title: str, content: str) -> str:
    """Auto-detect document category from title and content."""
    text = (title + " " + content[:500]).lower()
    best_cat = "general"
    best_score = 0

    for category, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_cat = category

    return best_cat


_PROGRAM_TYPE_MAP = {
    "hệ_thường": "tieu_chuan",
    "chính_quy": "tieu_chuan",
    "tiên_tiến": "tien_tien",
    "TIẾNG_ANH": "tieng_anh",
    "tiếng_anh": "tieng_anh",
    "nhật_bản": "nhat_ban",
    "chuyển_tiếp": "chuyen_tiep",
    "LIÊN_KẾT": "lien_ket",
    "kiểm_định": "kiem_dinh",
}


def _detect_program_type(filename: str) -> str:
    """Detect program type from CSV filename."""
    for pattern, prog_type in _PROGRAM_TYPE_MAP.items():
        if pattern.lower() in filename.lower():
            return prog_type
    return "general"
