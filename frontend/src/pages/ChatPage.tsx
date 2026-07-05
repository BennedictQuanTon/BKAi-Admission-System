import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMetadata, sendFeedback, WS_BASE } from "../lib/api";

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
  const [sessionId] = useState(() => crypto.randomUUID());
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
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
    <div className="max-w-5xl mx-auto h-[calc(100vh-73px)] flex flex-col">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-16">
            <h1 className="font-display text-3xl font-bold text-slate-900 mb-3">
              Xin chào, tôi là BkAI
            </h1>
            <p className="text-slate-600 text-lg mb-8">
              Hỏi tôi về tuyển sinh, ngành học, học phí, điểm chuẩn tại HCMUT
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => submitQuery(s)}
                  className="px-4 py-2 rounded-full border border-slate-200 bg-surface text-sm text-slate-700 hover:border-brand-500 hover:text-brand-700 transition"
                >
                  {s}
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
                className={`max-w-[85%] rounded-2xl px-4 py-3 shadow-sm ${
                  msg.role === "user"
                    ? "bg-brand-600 text-white"
                    : "bg-surface border border-slate-200 text-slate-800"
                }`}
              >
                {msg.role === "assistant" ? (
                  <div className="prose prose-slate max-w-none text-[16px] leading-relaxed">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content || (msg.streaming ? "..." : "")}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <p className="text-[16px]">{msg.content}</p>
                )}

                {msg.role === "assistant" && msg.metadata && !msg.streaming && (
                  <div className="mt-3 pt-3 border-t border-slate-200 space-y-2">
                    <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                      {msg.metadata.cached && <span className="px-2 py-1 bg-brand-50 rounded">Cache hit</span>}
                      {typeof msg.metadata.confidence === "number" && (
                        <span className="px-2 py-1 bg-white rounded border">
                          Confidence: {(msg.metadata.confidence * 100).toFixed(0)}%
                        </span>
                      )}
                      {typeof msg.metadata.response_time === "number" && (
                        <span className="px-2 py-1 bg-white rounded border">
                          {msg.metadata.response_time}s
                        </span>
                      )}
                    </div>
                    {msg.metadata.sources && msg.metadata.sources.length > 0 && (
                      <div>
                        <div className="text-xs font-semibold text-slate-600 mb-1">Nguồn tham khảo</div>
                        <ul className="text-xs text-slate-500 space-y-1">
                          {msg.metadata.sources.map((s) => (
                            <li key={s} className="truncate">• {s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {prevUser && !msg.metadata.guardrail && (
                      <div className="flex gap-2">
                        <button
                          type="button"
                          aria-label="Hữu ích"
                          onClick={() => sendFeedback(prevUser.content, "like")}
                          className="px-2 py-1 text-sm rounded border hover:bg-brand-50"
                        >
                          👍
                        </button>
                        <button
                          type="button"
                          aria-label="Không hữu ích"
                          onClick={() => sendFeedback(prevUser.content, "dislike")}
                          className="px-2 py-1 text-sm rounded border hover:bg-brand-50"
                        >
                          👎
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
          <div className="text-sm text-brand-700 font-medium px-2" aria-live="polite">
            {status}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-slate-200 p-4 bg-white">
        <div className="flex gap-3 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value.slice(0, 500))}
            rows={2}
            placeholder="Hỏi về tuyển sinh HCMUT..."
            className="flex-1 resize-none rounded-xl border border-slate-300 px-4 py-3 text-[16px] focus:outline-none focus:ring-2 focus:ring-brand-500"
            aria-label="Câu hỏi"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-5 py-3 rounded-xl bg-brand-600 text-white font-medium hover:bg-brand-700 disabled:opacity-50 transition"
          >
            Gửi
          </button>
        </div>
        <div className="text-xs text-slate-400 mt-2">{input.length}/500</div>
      </form>
    </div>
  );
}
