"""
BKAi Audio Service.

Provides Speech-to-Text (STT) via faster-whisper and
Text-to-Speech (TTS) via edge-tts, both running 100% locally/free.

Design:
    - Whisper model is lazy-loaded as a singleton (loaded once on first use).
    - STT runs synchronously in a thread pool to avoid blocking the event loop.
    - TTS is natively async (edge-tts uses aiohttp internally).
"""

from __future__ import annotations

import asyncio
import re
import os
from pathlib import Path

from utils.logger import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
WHISPER_MODEL_SIZE = "base"       # "tiny" (~40MB) or "base" (~150MB)
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"     # Quantized for CPU performance
WHISPER_LANGUAGE = "vi"           # Vietnamese

# Domain-specific prompt hint — biases Whisper decoder towards
# admissions vocabulary so "bắt khoa" → "Bách Khoa" etc.
WHISPER_INITIAL_PROMPT = (
    "Tư vấn tuyển sinh Đại học Bách Khoa, ĐHQG-HCM. "
    "Các ngành: Khoa học Máy tính, Công nghệ Thông tin, Cơ khí, "
    "Cơ điện tử, Điện - Điện tử, Kỹ thuật Hóa học, Quản lý Công nghiệp. "
    "Điểm chuẩn, chỉ tiêu, học phí, xét tuyển, ĐGNL, THPT, "
    "ký túc xá, học bổng, chương trình đào tạo."
)

TTS_VOICE = "vi-VN-HoaiMyNeural"  # Natural Vietnamese female voice
TTS_RATE = "+0%"                  # Speech rate adjustment
TTS_VOLUME = "+0%"                # Volume adjustment


# ──────────────────────────────────────────────
# Domain Post-Processing (Layer 2 & 3)
# ──────────────────────────────────────────────
# Common STT mistakes → correct domain terms
DOMAIN_CORRECTIONS: dict[str, str] = {
    # Tên trường
    "bắt khoa": "Bách Khoa",
    "bach khoa": "Bách Khoa",
    "bát khoa": "Bách Khoa",
    "bặt khoa": "Bách Khoa",
    "bậc khoa": "Bách Khoa",
    "bạch khoa": "Bách Khoa",
    # Viết tắt đọc thành chữ
    "đê hát cu gê": "ĐHQG",
    "đê hát cê gê": "ĐHQG",
    "đê gê n l": "ĐGNL",
    "đê gê nờ lờ": "ĐGNL",
    "cê n tê tê": "CNTT",
    "ka hát m tê": "KHMT",
    # Thuật ngữ tuyển sinh
    "xét tuyến": "xét tuyển",
    "tuyến sinh": "tuyển sinh",
    "chị tiêu": "chỉ tiêu",
    "chì tiêu": "chỉ tiêu",
    "điểm chuyển": "điểm chuẩn",
    "điểm chuẩng": "điểm chuẩn",
    "điểm chuẩ": "điểm chuẩn",
    "học phỉ": "học phí",
    "học phì": "học phí",
    "ngành hộc": "ngành học",
    "ngàng học": "ngành học",
    "kí túc xá": "ký túc xá",
    "kì túc xá": "ký túc xá",
    "học bỗng": "học bổng",
    "hộc bổng": "học bổng",
    # Tên ngành
    "cơ khỉ": "Cơ khí",
    "cơ khì": "Cơ khí",
    "khoa hộc máy tính": "Khoa học Máy tính",
    "công nghề thông tin": "Công nghệ Thông tin",
    "công nghệ thông tín": "Công nghệ Thông tin",
    "kỷ thuật": "kỹ thuật",
    "quản lí": "quản lý",
}

# Keywords indicating the query is about admissions domain
DOMAIN_KEYWORDS = {
    "bách khoa", "tuyển sinh", "điểm chuẩn", "ngành", "học phí",
    "chỉ tiêu", "xét tuyển", "đgnl", "thpt", "đại học", "chương trình",
    "ký túc xá", "học bổng", "thạc sĩ", "kỹ sư", "cơ khí", "cntt",
    "điện tử", "hóa học", "công nghệ", "khoa học", "máy tính",
    "nhập học", "hồ sơ", "đăng ký", "mã ngành", "trường",
}


def _domain_post_process(text: str) -> str:
    """
    Layer 2: Fix common STT mistakes for admissions domain.

    Scans the transcribed text for known misheard patterns and
    replaces them with the correct Vietnamese terms.
    """
    if not text:
        return text

    result = text
    for wrong, correct in DOMAIN_CORRECTIONS.items():
        # Case-insensitive full word replacement using lookarounds
        pattern = re.compile(r'(?<![\w])' + re.escape(wrong) + r'(?![\w])', re.IGNORECASE)
        result = pattern.sub(correct, result)

    return result.strip()


def _add_domain_context(text: str) -> str:
    """
    Layer 3: Append domain context hint if no keywords detected.

    Ensures the RAG pipeline understands the question is about
    HCMUT admissions even if the user's speech was vague.
    """
    text_lower = text.lower()
    if not any(kw in text_lower for kw in DOMAIN_KEYWORDS):
        return text + " (về tuyển sinh Đại học Bách Khoa)"
    return text


# ──────────────────────────────────────────────
# Whisper Model Singleton
# ──────────────────────────────────────────────
_whisper_model = None


def _get_whisper_model():
    """
    Get or initialize the faster-whisper model (singleton).

    The model is loaded once on first call and reused for all
    subsequent transcriptions to avoid repeated cold starts.
    """
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        logger.info(
            "whisper_model_loading",
            model=WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )

        _whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )

        logger.info("whisper_model_loaded")

    return _whisper_model


# ──────────────────────────────────────────────
# Speech-to-Text (STT)
# ──────────────────────────────────────────────
def _transcribe_sync(audio_path: str) -> dict:
    """
    Synchronous transcription using faster-whisper.

    This runs in a thread pool via asyncio.to_thread() to
    avoid blocking the FastAPI event loop.

    Args:
        audio_path: Path to audio file (WAV, MP3, WebM, etc.)

    Returns:
        Dict with 'text', 'language', 'duration' keys.
    """
    model = _get_whisper_model()

    segments, info = model.transcribe(
        audio_path,
        language=WHISPER_LANGUAGE,
        beam_size=5,
        initial_prompt=WHISPER_INITIAL_PROMPT,  # Layer 1: domain bias
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 200,
        },
    )

    # Collect all segment texts
    texts = []
    for segment in segments:
        texts.append(segment.text.strip())

    raw_text = " ".join(texts).strip()

    # Layer 2: Fix domain-specific misheard words
    corrected_text = _domain_post_process(raw_text)

    # Layer 3: Add domain context if no keywords found
    final_text = _add_domain_context(corrected_text)

    logger.info(
        "stt_post_process",
        raw=raw_text[:100],
        corrected=corrected_text[:100],
        final=final_text[:100],
    )

    return {
        "text": final_text,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration": round(info.duration, 2),
    }


async def speech_to_text(audio_path: str) -> dict:
    """
    Transcribe audio file to Vietnamese text (async wrapper).

    Runs Whisper in a background thread to not block the event loop.

    Args:
        audio_path: Path to audio file.

    Returns:
        Dict with:
            - text: Transcribed Vietnamese text.
            - language: Detected language code.
            - duration: Audio duration in seconds.
    """
    logger.info("stt_start", audio_path=audio_path)

    try:
        result = await asyncio.to_thread(_transcribe_sync, audio_path)

        logger.info(
            "stt_complete",
            text_length=len(result["text"]),
            language=result["language"],
            duration=result["duration"],
        )

        return result

    except Exception as e:
        logger.error("stt_error", error=str(e))
        raise


# ──────────────────────────────────────────────
# Text-to-Speech (TTS)
# ──────────────────────────────────────────────
def _clean_text_for_tts(text: str) -> str:
    """
    Clean text for natural TTS output.

    Removes markdown formatting, special characters, and
    excessive whitespace that would sound unnatural when spoken.
    """
    # Remove markdown bold/italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)

    # Remove markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove markdown links, keep text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # Remove bullet points
    text = re.sub(r"^[\-\*]\s+", "", text, flags=re.MULTILINE)

    # Remove numbered list markers
    text = re.sub(r"^\d+\.\s+", "", text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)

    # Clean special characters that TTS struggles with
    text = re.sub(r"[#_`~|>]", "", text)

    # Collapse multiple newlines/spaces
    text = re.sub(r"\n{2,}", ". ", text)
    text = re.sub(r"\n", " ", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


async def text_to_speech(text: str, output_path: str) -> str:
    """
    Synthesize Vietnamese speech from text using edge-tts.

    Edge-tts uses Microsoft Edge's online TTS service which is
    free and produces high-quality natural Vietnamese speech.

    Args:
        text: Vietnamese text to speak.
        output_path: Path to save the output MP3 file.

    Returns:
        Path to the generated audio file.
    """
    import edge_tts

    # Clean text for natural speech
    clean_text = _clean_text_for_tts(text)

    if not clean_text:
        clean_text = "Xin lỗi, tôi không thể xử lý câu trả lời này."

    # Truncate very long text for TTS (edge-tts has limits)
    if len(clean_text) > 3000:
        clean_text = clean_text[:3000] + "... Nội dung còn lại vui lòng đọc trên màn hình."

    logger.info(
        "tts_start",
        text_length=len(clean_text),
        voice=TTS_VOICE,
    )

    try:
        communicate = edge_tts.Communicate(
            text=clean_text,
            voice=TTS_VOICE,
            rate=TTS_RATE,
            volume=TTS_VOLUME,
        )

        await communicate.save(output_path)

        logger.info("tts_complete", output_path=output_path)
        return output_path

    except Exception as e:
        logger.error("tts_error", error=str(e))
        raise
