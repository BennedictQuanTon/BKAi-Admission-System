"""Vietnamese text tokenization helpers."""

from __future__ import annotations

try:
    from pyvi.ViTokenizer import tokenize as _pyvi_tokenize

    def tokenize_vi(text: str) -> list[str]:
        return _pyvi_tokenize(text).split()
except ImportError:
    def tokenize_vi(text: str) -> list[str]:
        return text.lower().split()
