import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "../lib/api";

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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const sessionId = useRef(`voice_${Date.now()}`);

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  useEffect(() => () => stopStream(), []);

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
    setStatus("Đang xử lý câu hỏi...");

    const ask = await fetch(`${API_BASE}/api/voice/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, session_id: sessionId.current }),
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
      setStatus("Nhấn mic để hỏi tiếp");
    };
    await audio.play();
  }, []);

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
      const volume = data.reduce((sum, v) => sum + Math.abs(v - 128), 0) / data.length / 128;
      if (volume < SILENCE_THRESHOLD) {
        silenceStart = silenceStart ?? Date.now();
        if (Date.now() - silenceStart > SILENCE_DURATION_MS) {
          recorder.stop();
          return;
        }
      } else {
        silenceStart = null;
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };

  const handleMic = () => {
    if (state === "idle") startRecording();
    else if (state === "recording") mediaRecorderRef.current?.stop();
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="font-display text-4xl md:text-5xl font-black tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-brand-600 via-indigo-600 to-blue-500 mb-2 text-center">
        BKAi Voice
      </h1>
      <p className="text-slate-500 font-medium text-sm md:text-base text-center mb-10">
        Hỏi bằng giọng nói về tuyển sinh HCMUT
      </p>

      <div className="flex flex-col items-center gap-6 mb-12">
        <div className="relative">
          {/* Audio wave pulse rings */}
          {state === "recording" && (
            <>
              <div className="absolute inset-0 rounded-full bg-red-500/20 animate-ping" />
              <div className="absolute -inset-4 rounded-full bg-red-500/10 animate-pulse" />
            </>
          )}
          {state === "speaking" && (
            <>
              <div className="absolute inset-0 rounded-full bg-brand-500/20 animate-ping" />
              <div className="absolute -inset-4 rounded-full bg-brand-500/10 animate-pulse" />
            </>
          )}
          <button
            type="button"
            onClick={handleMic}
            disabled={state === "transcribing" || state === "thinking" || state === "speaking"}
            className={`relative w-28 h-28 rounded-full text-white text-3xl shadow-xl flex items-center justify-center transition-all duration-300 hover:scale-105 ${
              state === "recording"
                ? "bg-gradient-to-tr from-red-600 to-rose-500 shadow-red-500/25"
                : state === "speaking"
                ? "bg-gradient-to-tr from-brand-600 to-indigo-600 shadow-brand-500/25"
                : "bg-gradient-to-tr from-brand-600 to-indigo-600 shadow-brand-500/20 hover:shadow-brand-500/30"
            }`}
            aria-label="Microphone"
          >
            {state === "recording" ? (
              <svg className="w-10 h-10 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
              </svg>
            ) : (
              <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            )}
          </button>
        </div>
        <p className="text-brand-600 font-semibold text-xs tracking-wide uppercase px-4 py-1.5 rounded-full bg-brand-50 border border-brand-100/50 animate-pulse" aria-live="polite">
          {status}
        </p>
      </div>

      <div className="space-y-4 max-w-2xl mx-auto">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] px-4 py-3.5 shadow-sm transition-all duration-300 ${
                msg.role === "user"
                  ? "bg-gradient-to-tr from-brand-600 via-brand-600 to-indigo-600 text-white rounded-2xl rounded-tr-sm"
                  : "bg-white/80 backdrop-blur-sm border border-slate-200/60 text-slate-800 rounded-2xl rounded-tl-sm"
              }`}
            >
              <div className={`text-[10px] uppercase tracking-wider mb-1.5 font-bold ${msg.role === "user" ? "text-white/80" : "text-slate-400"}`}>
                {msg.role === "user" ? "Bạn" : "BKAi"}
              </div>
              <p className="text-[15px] leading-relaxed">{msg.text}</p>
              {msg.audioUrl && (
                <div className="mt-3.5 pt-3 border-t border-slate-100">
                  <audio controls src={msg.audioUrl} className="w-full h-8 accent-brand-600" />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
