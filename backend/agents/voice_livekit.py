"""
BkAI LiveKit Voice Worker (backend/agents/voice_livekit.py)

Stack:
- LiveKit WebRTC + Silero VAD
- Deepgram Nova STT (Vietnamese) when DEEPGRAM_API_KEY is set
- Fallback: local faster-whisper STT
- Brain: FastAPI counselor + Agentic RAG (channel=voice)
- TTS: edge-tts Vietnamese (NOT Deepgram Aura — no VI support)

Run (from backend/):
  source .venv/bin/activate
  pip install -r requirements.txt
  python -m agents.voice_livekit download-files
  python -m agents.voice_livekit dev
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

BACKEND_URL = os.getenv("BKAI_BACKEND_URL", "http://127.0.0.1:8000")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_STT_MODEL = os.getenv("DEEPGRAM_STT_MODEL", "nova-3")
DEEPGRAM_LANGUAGE = os.getenv("DEEPGRAM_LANGUAGE", "vi")

logger = logging.getLogger("bkai-voice")


async def ask_counselor(text: str, session_id: str) -> str:
    async with httpx.AsyncClient(timeout=120.0) as client:
        res = await client.post(
            f"{BACKEND_URL}/api/chat",
            json={"query": text[:500], "session_id": session_id, "channel": "voice"},
        )
        res.raise_for_status()
        return res.json().get("answer", "")


def main() -> None:
    from livekit.agents import (
        Agent,
        AgentSession,
        AutoSubscribe,
        JobContext,
        WorkerOptions,
        cli,
        llm,
        stt,
        tts,
        APIConnectOptions,
    )
    from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
    from livekit.plugins import silero

    def build_stt():
        if DEEPGRAM_API_KEY:
            from livekit.plugins import deepgram

            logger.info(
                "stt_provider=deepgram model=%s language=%s",
                DEEPGRAM_STT_MODEL,
                DEEPGRAM_LANGUAGE,
            )
            return deepgram.STT(
                model=DEEPGRAM_STT_MODEL,
                language=DEEPGRAM_LANGUAGE,
                api_key=DEEPGRAM_API_KEY,
            )

        logger.warning("DEEPGRAM_API_KEY missing — falling back to local Whisper STT")

        class WhisperSTT(stt.STT):
            def __init__(self) -> None:
                super().__init__(
                    capabilities=stt.STTCapabilities(streaming=False, interim_results=False)
                )

            async def _recognize_impl(
                self,
                buffer,
                *,
                language=None,
                conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
            ) -> stt.SpeechEvent:
                from livekit.agents.utils import audio as audio_utils
                from services.audio_service import speech_to_text
                import wave
                import numpy as np

                frames = audio_utils.merge_frames(buffer)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    path = tmp.name
                try:
                    audio_data = np.frombuffer(frames.data, dtype=np.int16)
                    with wave.open(path, "wb") as wf:
                        wf.setnchannels(frames.num_channels or 1)
                        wf.setsampwidth(2)
                        wf.setframerate(frames.sample_rate or 16000)
                        wf.writeframes(audio_data.tobytes())
                    result = await speech_to_text(path)
                    text = result.get("text", "")
                finally:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

                return stt.SpeechEvent(
                    type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[stt.SpeechData(text=text or "", language=language or "vi")],
                )

        return WhisperSTT()

    class EdgeTTS(tts.TTS):
        def __init__(self) -> None:
            super().__init__(
                capabilities=tts.TTSCapabilities(streaming=False),
                sample_rate=24000,
                num_channels=1,
            )

        def synthesize(
            self,
            text: str,
            *,
            conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        ):
            return _EdgeTTSStream(text=text, tts=self, conn_options=conn_options)

    class _EdgeTTSStream(tts.ChunkedStream):
        async def _run(self, output_emitter) -> None:
            from services.audio_service import text_to_speech
            from livekit import rtc

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                path = tmp.name
            try:
                await text_to_speech(self._input_text, path)
                try:
                    import av

                    container = av.open(path)
                    stream = container.streams.audio[0]
                    resampler = av.audio.resampler.AudioResampler(
                        format="s16", layout="mono", rate=24000
                    )
                    for frame in container.decode(stream):
                        resampled = resampler.resample(frame)
                        frames = resampled if isinstance(resampled, list) else [resampled]
                        for pcm in frames:
                            if pcm is None:
                                continue
                            data = pcm.to_ndarray().tobytes()
                            output_emitter.push(
                                rtc.AudioFrame(
                                    data=data,
                                    sample_rate=24000,
                                    num_channels=1,
                                    samples_per_channel=max(len(data) // 2, 1),
                                )
                            )
                    output_emitter.flush()
                except Exception as e:
                    logger.error("edge_tts_decode_failed error=%s", e)
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    class BackendLLM(llm.LLM):
        def __init__(self, session_id: str) -> None:
            super().__init__()
            self._session_id = session_id

        def chat(self, *, chat_ctx: llm.ChatContext, tools=None, conn_options=None, **kwargs):
            return _BackendLLMStream(
                self,
                chat_ctx=chat_ctx,
                tools=tools or [],
                session_id=self._session_id,
            )

    class _BackendLLMStream(llm.LLMStream):
        def __init__(self, llm_obj, *, chat_ctx, tools, session_id: str):
            super().__init__(llm_obj, chat_ctx=chat_ctx, tools=tools)
            self._session_id = session_id

        async def _run(self) -> None:
            text = ""
            for item in reversed(self.chat_ctx.items):
                if getattr(item, "role", None) == "user":
                    content = getattr(item, "content", "")
                    if isinstance(content, list):
                        text = " ".join(str(c) for c in content if isinstance(c, str))
                    else:
                        text = str(content or "")
                    break
            try:
                answer = await ask_counselor(text or "Xin chào", self._session_id)
            except Exception:
                logger.exception("counselor_call_failed")
                answer = "Xin lỗi, mình gặp sự cố. Bạn thử lại giúp mình nhé."

            from livekit.agents.llm import ChatChunk, ChoiceDelta

            self._event_ch.send_nowait(
                ChatChunk(id="bkai", delta=ChoiceDelta(role="assistant", content=answer))
            )

    class CounselorAgent(Agent):
        def __init__(self) -> None:
            super().__init__(
                instructions=(
                    "Bạn là BkAI — cố vấn tuyển sinh HCMUT. "
                    "Nói tiếng Việt ngắn gọn, xưng mình/bạn."
                )
            )

    async def entrypoint(ctx: JobContext) -> None:
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        session_id = (ctx.room.name or "voice_default").replace("bkai-", "", 1)

        session = AgentSession(
            vad=silero.VAD.load(),
            stt=build_stt(),
            llm=BackendLLM(session_id=session_id),
            tts=EdgeTTS(),
        )
        await session.start(agent=CounselorAgent(), room=ctx.room)
        await session.generate_reply(
            instructions=(
                "Chào bạn một câu ngắn bằng tiếng Việt và hỏi bạn cần tư vấn tuyển sinh gì."
            )
        )

    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except ImportError as e:
        print(
            "Install deps: pip install -r backend/requirements.txt\n"
            f"{e}",
            file=sys.stderr,
        )
        sys.exit(1)
