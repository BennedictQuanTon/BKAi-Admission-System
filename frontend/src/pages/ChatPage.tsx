import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMetadata, sendFeedback, WS_BASE, getSessionId } from "../lib/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  metadata?: ChatMetadata;
};

const SUGGESTIONS = [
  "Điểm chuẩn ngành Khoa học Máy tính mã 106?",
  "Học phí chương trình Tiếng Anh?",
  "Chỉ tiêu tuyển sinh năm 2025?",
  "Phương thức xét tuyển ĐGNL tại HCMUT?",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId] = useState(() => getSessionId());
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messages.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, status]);

  useEffect(() => {
    const ws = new WebSocket(`${WS_BASE}/ws/chat`);
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  async function submitQuery(query: string) {
    if (!query.trim() || loading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: query.trim(),
    };
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: "assistant", content: "", streaming: true },
    ]);
    setInput("");
    setLoading(true);
    setStatus("Đang kết nối...");

    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "status") {
          setStatus(data.message);
        } else if (data.type === "token") {
          setStatus("Đang viết câu trả lời...");
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + data.content, streaming: true }
                : m,
            ),
          );
        } else if (data.type === "done") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: data.answer,
                    streaming: false,
                    metadata: data.metadata,
                  }
                : m,
            ),
          );
          setStatus("");
          setLoading(false);
          ws.onmessage = null;
        } else if (data.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: data.message, streaming: false }
                : m,
            ),
          );
          setStatus("");
          setLoading(false);
          ws.onmessage = null;
        }
      };
      ws.send(JSON.stringify({ query: query.trim(), session_id: sessionId }));
      return;
    }

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || "http://localhost:8000"}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), session_id: sessionId }),
      });
      const data = await res.json();
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: data.answer,
                streaming: false,
                metadata: {
                  cached: data.cached,
                  confidence: data.confidence,
                  sources: data.sources,
                  timings: data.timings,
                  guardrail: data.timings?.guardrail,
                },
              }
            : m,
        ),
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: "Không thể kết nối backend.", streaming: false }
            : m,
        ),
      );
    } finally {
      setStatus("");
      setLoading(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submitQuery(input);
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      <div className={`flex-1 min-h-0 px-4 py-6 max-w-5xl w-full mx-auto ${
        messages.length === 0
          ? "overflow-hidden flex flex-col justify-center"
          : "overflow-y-auto space-y-4"
      }`}>
        {messages.length === 0 && (
          <div className="relative max-w-4xl mx-auto py-8 w-full flex flex-col justify-center min-h-[500px]">
            {/* Ambient background glow inside the chat container for extra depth */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[350px] h-[350px] bg-blue-400/5 rounded-full blur-[80px] pointer-events-none" />

            {/* Floating Suggestions - Left Side */}
            <div className="hidden lg:block absolute left-0 top-12 transform -translate-x-12 max-w-[260px] w-full">
              <button
                type="button"
                onClick={() => submitQuery(SUGGESTIONS[0])}
                className="group relative flex items-center justify-center p-6 rounded-2xl border border-white/40 bg-white/20 backdrop-blur-md text-center hover:border-brand-500/40 hover:bg-white/35 hover:shadow-lg hover:shadow-brand-500/5 transition-all duration-300 hover:-translate-y-1 cursor-pointer min-h-[90px] w-full shadow-[0_8px_32px_rgba(31,41,55,0.03),inset_0_1px_1px_rgba(255,255,255,0.7)]"
              >
                <span className="text-[15px] font-semibold text-slate-700 leading-snug group-hover:text-slate-900">{SUGGESTIONS[0]}</span>
              </button>
            </div>

            <div className="hidden lg:block absolute left-0 bottom-12 transform -translate-x-16 max-w-[260px] w-full">
              <button
                type="button"
                onClick={() => submitQuery(SUGGESTIONS[2])}
                className="group relative flex items-center justify-center p-6 rounded-2xl border border-white/40 bg-white/20 backdrop-blur-md text-center hover:border-brand-500/40 hover:bg-white/35 hover:shadow-lg hover:shadow-brand-500/5 transition-all duration-300 hover:-translate-y-1 cursor-pointer min-h-[90px] w-full shadow-[0_8px_32px_rgba(31,41,55,0.03),inset_0_1px_1px_rgba(255,255,255,0.7)]"
              >
                <span className="text-[15px] font-semibold text-slate-700 leading-snug group-hover:text-slate-900">{SUGGESTIONS[2]}</span>
              </button>
            </div>

            {/* Floating Suggestions - Right Side */}
            <div className="hidden lg:block absolute right-0 top-8 transform translate-x-12 max-w-[260px] w-full">
              <button
                type="button"
                onClick={() => submitQuery(SUGGESTIONS[1])}
                className="group relative flex items-center justify-center p-6 rounded-2xl border border-white/40 bg-white/20 backdrop-blur-md text-center hover:border-brand-500/40 hover:bg-white/35 hover:shadow-lg hover:shadow-brand-500/5 transition-all duration-300 hover:-translate-y-1 cursor-pointer min-h-[90px] w-full shadow-[0_8px_32px_rgba(31,41,55,0.03),inset_0_1px_1px_rgba(255,255,255,0.7)]"
              >
                <span className="text-[15px] font-semibold text-slate-700 leading-snug group-hover:text-slate-900">{SUGGESTIONS[1]}</span>
              </button>
            </div>

            <div className="hidden lg:block absolute right-0 bottom-8 transform translate-x-16 max-w-[260px] w-full">
              <button
                type="button"
                onClick={() => submitQuery(SUGGESTIONS[3])}
                className="group relative flex items-center justify-center p-6 rounded-2xl border border-white/40 bg-white/20 backdrop-blur-md text-center hover:border-brand-500/40 hover:bg-white/35 hover:shadow-lg hover:shadow-brand-500/5 transition-all duration-300 hover:-translate-y-1 cursor-pointer min-h-[90px] w-full shadow-[0_8px_32px_rgba(31,41,55,0.03),inset_0_1px_1px_rgba(255,255,255,0.7)]"
              >
                <span className="text-[15px] font-semibold text-slate-700 leading-snug group-hover:text-slate-900">{SUGGESTIONS[3]}</span>
              </button>
            </div>

            {/* Center Welcome Text */}
            <div className="text-center relative z-10 px-4 max-w-3xl mx-auto mb-10 lg:mb-0">
              <h1 className="font-display text-5xl md:text-6xl lg:text-7xl font-black tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-brand-600 via-indigo-600 to-blue-500 mb-6 leading-tight">
                Xin chào, tôi là BKAi
              </h1>
              <p className="text-slate-500 font-semibold text-base md:text-lg lg:text-xl max-w-2xl mx-auto leading-relaxed">
                Hỏi tôi về tuyển sinh, ngành học, học phí, điểm chuẩn tại HCMUT
              </p>
            </div>

            {/* Grid Fallback for Tablet / Mobile */}
            <div className="flex lg:hidden flex-col gap-2.5 max-w-md mx-auto w-full px-4 relative z-10">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => submitQuery(s)}
                  className="flex items-center justify-center px-5 py-4 rounded-2xl border border-white/40 bg-white/20 backdrop-blur-md hover:bg-white/35 hover:border-brand-500/40 hover:text-brand-700 text-sm font-semibold text-slate-700 text-center transition shadow-[0_8px_32px_rgba(31,41,55,0.03),inset_0_1px_1px_rgba(255,255,255,0.7)] hover:shadow-brand-500/5 min-h-[60px]"
                >
                  <span className="leading-snug">{s}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const prevUser =
            msg.role === "assistant"
              ? [...messages].slice(0, idx).reverse().find((m) => m.role === "user")
              : null;
          return (
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
                {msg.role === "assistant" ? (
                  <div className="prose prose-slate max-w-none text-[15px] leading-relaxed">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content || (msg.streaming ? "..." : "")}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p className="text-[15px] leading-relaxed">{msg.content}</p>
                )}

                {msg.role === "assistant" && msg.metadata && !msg.streaming && (
                  <div className="mt-4 pt-3.5 border-t border-slate-100 space-y-3">
                    <div className="flex flex-wrap gap-2 text-[10px] text-slate-400">
                      {msg.metadata.cached && <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-100 rounded-md font-medium">Cache hit</span>}
                      {typeof msg.metadata.confidence === "number" && (
                        <span className="px-2 py-0.5 bg-slate-50 border border-slate-100 rounded-md">
                          Confidence: {(msg.metadata.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                      {typeof msg.metadata.response_time === "number" && (
                        <span className="px-2 py-0.5 bg-slate-50 border border-slate-100 rounded-md">
                          Time: {msg.metadata.response_time}s
                        </span>
                      )}
                    </div>
                    {msg.metadata.sources && msg.metadata.sources.length > 0 && (
                      <div className="bg-slate-50/50 p-2.5 rounded-xl border border-slate-100">
                        <div className="text-[11px] font-bold text-slate-500 mb-1.5 flex items-center gap-1">
                          <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                          </svg>
                          Nguồn tham khảo
                        </div>
                        <ul className="text-[11px] text-slate-500 space-y-1">
                          {msg.metadata.sources.map((s) => (
                            <li key={s} className="truncate">• {s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {prevUser && !msg.metadata.guardrail && (
                      <div className="flex gap-2 pt-1">
                        <button
                          type="button"
                          aria-label="Hữu ích"
                          onClick={() => sendFeedback(prevUser.content, "like")}
                          className="px-2.5 py-1 text-xs rounded-lg border border-slate-200 bg-white hover:bg-brand-50 hover:text-brand-700 transition flex items-center gap-1"
                        >
                          👍 Hữu ích
                        </button>
                        <button
                          type="button"
                          aria-label="Không hữu ích"
                          onClick={() => sendFeedback(prevUser.content, "dislike")}
                          className="px-2.5 py-1 text-xs rounded-lg border border-slate-200 bg-white hover:bg-brand-50 hover:text-brand-700 transition flex items-center gap-1"
                        >
                          👎 Không hữu ích
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {status && (
          <div className="text-xs text-brand-600 font-semibold px-2 animate-pulse" aria-live="polite">
            {status}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-slate-200/60 p-4 bg-white/40 backdrop-blur-md relative z-20 shrink-0">
        <div className="max-w-4xl mx-auto relative flex items-center bg-white border border-slate-200 rounded-2xl shadow-lg shadow-slate-100/50 p-1.5 focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-500/10 transition-all">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value.slice(0, 500))}
            placeholder="Hỏi về tuyển sinh, điểm chuẩn, học phí..."
            rows={1}
            className="flex-1 bg-transparent border-0 px-4 py-3 text-slate-800 placeholder-slate-400 focus:ring-0 focus:outline-none resize-none text-[15px] max-h-32 min-h-[48px]"
            aria-label="Câu hỏi"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitQuery(input);
              }
            }}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-5 py-3 rounded-xl bg-gradient-to-r from-brand-600 to-indigo-600 text-white font-semibold text-sm hover:from-brand-700 hover:to-indigo-700 disabled:opacity-40 transition shadow-sm hover:shadow-brand-500/10 cursor-pointer flex items-center justify-center gap-1.5 self-end"
          >
            <span>Gửi</span>
            <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
              <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
            </svg>
          </button>
        </div>
        <div className="max-w-4xl mx-auto flex justify-between items-center text-[10px] text-slate-400 mt-2 px-1">
          <span>BKAi có thể trả lời chưa hoàn toàn chính xác. Hãy kiểm tra thông tin chính thức.</span>
          <span>{input.length}/500</span>
        </div>
      </form>
    </div>
  );
}
