import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_BASE,
  clearServerSession,
  getSessionId,
  newSessionId,
} from "../lib/api";

type VoiceMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  audioUrl?: string;
};

const SILENCE_THRESHOLD = 0.015;
const SILENCE_DURATION_MS = 1800;

export default function VoicePage() {
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [state, setState] = useState<"idle" | "recording" | "transcribing" | "thinking" | "speaking">("idle");
  const [status, setStatus] = useState("Nhấn mic để bắt đầu");
  const [sessionId, setSessionId] = useState(() => getSessionId());
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  useEffect(() => () => stopStream(), []);

  async function startNewSession() {
    stopStream();
    await clearServerSession(sessionId);
    const sid = newSessionId();
    setSessionId(sid);
    setMessages([]);
    setState("idle");
    setStatus("Nhấn mic để bắt đầu đoạn tư vấn mới");
  }

  const processRecording = useCallback(async (blob: Blob) => {
    setState("transcribing");
    setStatus("Đang nhận diện giọng nói...");

    const form = new FormData();
    form.append("audio", blob, "recording.webm");

    const transcribe = await fetch(`${API_BASE}/api/voice/transcribe`, { method: "POST", body: form });
    if (!transcribe.ok) {
      setState("idle");
      setStatus("Không nhận diện được giọng nói");
      return;
    }
    const { text } = await transcribe.json();
    const userMsg: VoiceMessage = { id: crypto.randomUUID(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);

    setState("thinking");
    setStatus("Đang tư vấn...");

    const ask = await fetch(`${API_BASE}/api/voice/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, session_id: sessionId, channel: "voice" }),
    });

    if (!ask.ok) {
      setState("idle");
      setStatus("Lỗi xử lý câu hỏi");
      return;
    }

    const answerText = decodeURIComponent(ask.headers.get("X-Answer-Text") || "");
    const audioBlob = await ask.blob();
    const audioUrl = URL.createObjectURL(audioBlob);
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", text: answerText, audioUrl }]);

    setState("speaking");
    setStatus("Đang phát câu trả lời...");
    const audio = new Audio(audioUrl);
    audio.onended = () => {
      setState("idle");
      setStatus("Nhấn mic để hỏi tiếp (mình vẫn nhớ đoạn chat này)");
    };
    await audio.play();
  }, [sessionId]);

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;
    const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    chunksRef.current = [];
    recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
    recorder.onstop = async () => {
      stopStream();
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      if (blob.size > 0) await processRecording(blob);
    };
    mediaRecorderRef.current = recorder;
    recorder.start();
    setState("recording");
    setStatus("Đang nghe... nói câu hỏi tuyển sinh HCMUT");

    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    source.connect(analyser);
    let silenceStart: number | null = null;
    const tick = () => {
      if (recorder.state !== "recording") return;
      const data = new Uint8Array(analyser.fftSize);
      analyser.getByteTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / data.length);
      if (rms < SILENCE_THRESHOLD) {
        if (silenceStart == null) silenceStart = Date.now();
        else if (Date.now() - silenceStart > SILENCE_DURATION_MS) {
          recorder.stop();
          ctx.close();
          return;
        }
      } else {
        silenceStart = null;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col max-w-3xl w-full mx-auto px-4 py-8">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="font-display text-3xl font-bold text-slate-900 mb-2">BKAi Voice</h1>
          <p className="text-slate-500 text-sm">
            Tư vấn tuyển sinh bằng giọng nói (Whisper + counselor). Mình nhớ ngữ cảnh trong đoạn này;
            bấm “Đoạn mới” để xóa.
          </p>
        </div>
        <button
          type="button"
          onClick={startNewSession}
          className="shrink-0 text-sm font-semibold text-slate-600 hover:text-brand-700 px-3 py-1.5 rounded-lg border border-slate-200 bg-white"
        >
          Đoạn mới
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 mb-8">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] px-4 py-3 rounded-2xl ${
                msg.role === "user"
                  ? "bg-brand-600 text-white"
                  : "bg-white border border-slate-200 text-slate-800"
              }`}
            >
              <p className="text-sm leading-relaxed">{msg.text}</p>
              {msg.audioUrl && (
                <audio controls src={msg.audioUrl} className="w-full h-8 accent-brand-600 mt-2" />
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col items-center gap-3">
        <button
          type="button"
          disabled={state !== "idle"}
          onClick={startRecording}
          className={`w-20 h-20 rounded-full flex items-center justify-center text-white shadow-lg transition ${
            state === "recording"
              ? "bg-rose-500 animate-pulse"
              : state === "idle"
                ? "bg-brand-600 hover:bg-brand-700"
                : "bg-slate-400"
          }`}
        >
          Mic
        </button>
        <p className="text-sm text-slate-500">{status}</p>
      </div>
    </div>
  );
}
