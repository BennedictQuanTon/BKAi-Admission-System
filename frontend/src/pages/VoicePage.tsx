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
      <h1 className="font-display text-3xl font-bold text-slate-900 mb-2">BkAI Voice</h1>
      <p className="text-slate-600 mb-8">Hỏi bằng giọng nói về tuyển sinh HCMUT</p>

      <div className="flex flex-col items-center gap-4 mb-8">
        <button
          type="button"
          onClick={handleMic}
          disabled={state === "transcribing" || state === "thinking" || state === "speaking"}
          className={`w-28 h-28 rounded-full text-white text-3xl font-bold shadow-lg transition ${
            state === "recording" ? "bg-red-600 animate-pulse" : "bg-brand-600 hover:bg-brand-700"
          }`}
          aria-label="Microphone"
        >
          🎙️
        </button>
        <p className="text-brand-700 font-medium" aria-live="polite">{status}</p>
      </div>

      <div className="space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`rounded-2xl p-4 ${msg.role === "user" ? "bg-brand-50" : "bg-surface border"}`}>
            <div className="text-xs uppercase text-slate-500 mb-1">{msg.role === "user" ? "Bạn" : "BkAI"}</div>
            <p className="text-[16px]">{msg.text}</p>
            {msg.audioUrl && (
              <audio controls src={msg.audioUrl} className="mt-3 w-full" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
