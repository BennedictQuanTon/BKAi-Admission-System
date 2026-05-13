"""
BKAi Metadata Tagger.

Enriches document chunks with structured metadata for
intelligent filtering during retrieval.
"""

from __future__ import annotations

import re

from ingestion.loader import Document
from utils.logger import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────
# Year extraction patterns
# ──────────────────────────────────────────────
_YEAR_PATTERN = re.compile(r"\b(202[0-9])\b")
_ACADEMIC_YEAR_PATTERN = re.compile(r"\b(202[0-9])\s*[-–]\s*(202[0-9])\b")


def extract_years(text: str) -> list[str]:
    """Extract all year references from text."""
    years = set()
    for match in _ACADEMIC_YEAR_PATTERN.finditer(text):
        years.add(match.group(1))
        years.add(match.group(2))
    for match in _YEAR_PATTERN.finditer(text):
        years.add(match.group(1))
    return sorted(years)


# ──────────────────────────────────────────────
# Major code extraction
# ──────────────────────────────────────────────
_MAJOR_CODE_PATTERN = re.compile(r"\b([1-4]\d{2})\b")


def extract_major_codes(text: str) -> list[str]:
    """Extract 3-digit major codes (100-499 range)."""
    codes = set()
    for match in _MAJOR_CODE_PATTERN.finditer(text):
        code = match.group(1)
        code_int = int(code)
        if 100 <= code_int <= 499:
            codes.add(code)
    return sorted(codes)


# ──────────────────────────────────────────────
# Keyword extraction
# ──────────────────────────────────────────────
_IMPORTANT_TERMS = [
    "khoa học máy tính", "kỹ thuật máy tính", "điện tử", "cơ khí",
    "cơ điện tử", "xây dựng", "kiến trúc", "hóa học", "thực phẩm",
    "sinh học", "môi trường", "dầu khí", "vật liệu", "logistics",
    "quản lý công nghiệp", "ô tô", "hàng không", "nhiệt", "dệt may",
    "bán dẫn", "vi mạch", "hạt nhân", "đường sắt", "địa chất",
    "trí tuệ nhân tạo", "công nghệ thông tin", "khoa học dữ liệu",
    "quản trị kinh doanh", "kinh tế xây dựng", "kinh tế tuần hoàn",
    "điểm chuẩn", "học phí", "tuyển sinh", "xét tuyển", "chỉ tiêu",
    "đánh giá năng lực", "tốt nghiệp thpt", "học bạ", "ielts",
    "tiêu chuẩn", "tiếng anh", "tiên tiến", "nhật bản",
    "chuyển tiếp quốc tế", "liên kết quốc tế", "pfiev", "tài năng",
    "học bổng", "ký túc xá", "miễn giảm",
]


def extract_keywords(text: str) -> list[str]:
    """Extract domain-specific keywords from text."""
    text_lower = text.lower()
    found = [term for term in _IMPORTANT_TERMS if term in text_lower]
    return found[:10]  # Cap at 10 keywords per chunk


# ──────────────────────────────────────────────
# Score detection
# ──────────────────────────────────────────────
_SCORE_PATTERN = re.compile(r"\b(\d{2}\.\d{1,2})\b")


def has_score_data(text: str) -> bool:
    """Check if text contains admission score data (XX.XX format)."""
    scores = _SCORE_PATTERN.findall(text)
    # Filter to valid score range (40-100)
    valid = [s for s in scores if 40.0 <= float(s) <= 100.0]
    return len(valid) >= 2  # At least 2 scores suggests a data table


# ──────────────────────────────────────────────
# Main tagger
# ──────────────────────────────────────────────
def enrich_metadata(doc: Document) -> Document:
    """
    Enrich a document's metadata with auto-extracted tags.

    Adds: years, major_codes, keywords, has_scores, content_length.
    """
    text = doc.content

    # Extract and merge metadata
    years = extract_years(text)
    if years:
        doc.metadata["years"] = ",".join(years)

    major_codes = extract_major_codes(text)
    if major_codes:
        doc.metadata["major_codes"] = ",".join(major_codes)

    keywords = extract_keywords(text)
    if keywords:
        doc.metadata["keywords"] = ",".join(keywords)

    doc.metadata["has_scores"] = str(has_score_data(text))
    doc.metadata["content_length"] = str(len(text))

    return doc


def tag_all_documents(documents: list[Document]) -> list[Document]:
    """Enrich metadata for a list of documents."""
    tagged = [enrich_metadata(doc) for doc in documents]
    logger.info(
        "metadata_tagging_complete",
        total_docs=len(tagged),
        with_scores=sum(1 for d in tagged if d.metadata.get("has_scores") == "True"),
        with_years=sum(1 for d in tagged if "years" in d.metadata),
    )
    return tagged
