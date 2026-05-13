"""
BKAi Text Cleaning Utilities.
"""

from __future__ import annotations

import re
import unicodedata


def normalize_unicode(text: str) -> str:
    """Normalize Unicode text to NFC form."""
    return unicodedata.normalize("NFC", text)


def strip_markdown_formatting(text: str) -> str:
    """Remove markdown formatting artifacts while preserving content."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def clean_table_text(text: str) -> str:
    """Clean table-specific formatting for better chunk readability."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if re.match(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$", line):
            continue
        if "|" in line:
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if cells:
                cleaned.append(" | ".join(cells))
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


ABBREVIATIONS = {
    "ĐHQG-HCM": "Đại học Quốc gia TP.HCM",
    "ĐGNL": "Đánh giá Năng lực",
    "THPT": "Trung học Phổ thông",
    "KHMT": "Khoa học Máy tính",
    "CNTT": "Công nghệ Thông tin",
    "UTXT": "Ưu tiên xét tuyển",
    "CTĐT": "Chương trình đào tạo",
    "PFIEV": "Kỹ sư Chất lượng cao Việt-Pháp",
    "TNE": "Liên kết Cử nhân Quốc tế",
    "KTX": "Ký túc xá",
    "CNCN": "Công nghệ Công nghiệp",
}


def expand_abbreviations(text: str) -> str:
    """Expand common HCMUT abbreviations (first occurrence only)."""
    for abbr, full in ABBREVIATIONS.items():
        pattern = rf"\b{re.escape(abbr)}\b"
        text = re.sub(pattern, f"{abbr} ({full})", text, count=1)
    return text


def sanitize_input(text: str, max_length: int = 500) -> str:
    """Sanitize user input: strip control chars, enforce length limit."""
    text = "".join(
        c for c in text if unicodedata.category(c)[0] != "C" or c in "\n\t"
    )
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]


def extract_year_from_query(query: str) -> str | None:
    """Extract year reference from user query for metadata filtering."""
    match = re.search(r"\b(202[0-9])\b", query)
    return match.group(1) if match else None
