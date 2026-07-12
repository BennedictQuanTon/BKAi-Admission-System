import { useEffect, useState, useRef } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Cell,
} from "recharts";
import { fetchHealth, fetchStats, fetchStatsHistory, WS_BASE, getSessionId } from "../lib/api";

const COLORS = ["#10b981", "#f59e0b", "#ef4444"]; // Green (Đúng), Yellow (Chưa đánh giá), Red (Sai)

type LogEntry = {
  time: string;
  step: string;
  status: string;
  message: string;
  elapsed?: number;
};

const STEP_TRANSLATIONS: Record<string, string> = {
  start: "Khởi tạo",
  guardrail: "Guardrails (An toàn)",
  cache: "Semantic Cache (Bộ nhớ đệm)",
  query_rewrite: "Query Rewrite (Tối ưu câu hỏi)",
  retrieve: "Retrieval (Truy vấn tài liệu RAG)",
  evaluate_results: "Evaluation (Đánh giá tài liệu)",
  generate: "Generation (LLM Sinh câu trả lời)",
  self_reflect: "Self-Reflection (Tự đánh giá)",
  complete: "Hoàn thành",
  error: "Lỗi hệ thống",
};

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [healthy, setHealthy] = useState(true);

  // Real-time logs states
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [activeQuery, setActiveQuery] = useState<string | null>(null);
  const [activeTime, setActiveTime] = useState<number>(0);
  const [isRunning, setIsRunning] = useState(false);

  const currentSessionId = getSessionId();
  const timerRef = useRef<any>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function load() {
      try {
        const [s, h, health] = await Promise.all([
          fetchStats(),
          fetchStatsHistory(24),
          fetchHealth(),
        ]);
        setStats(s);
        setHistory(h.history || []);
        setHealthy(health.status === "healthy");
      } catch {
        setHealthy(false);
      }
    }
    load();
    const intervalId = setInterval(load, 10000);

    // WebSocket for real-time progress logs
    const ws = new WebSocket(`${WS_BASE}/ws/dashboard`);
    let startTime = 0;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "progress" && data.session_id === currentSessionId) {
          const logTime = new Date(data.timestamp * 1000).toLocaleTimeString("vi-VN");

          if (data.step === "start") {
            setLogs([]);
            setActiveQuery(data.query || "Đang xử lý câu hỏi...");
            setIsRunning(true);
            setActiveTime(0);
            startTime = Date.now();
            if (timerRef.current) clearInterval(timerRef.current);
            timerRef.current = setInterval(() => {
              setActiveTime(Math.round((Date.now() - startTime) / 100) / 10);
            }, 100);
          }

          setLogs((prev) => [
            ...prev,
            {
              time: logTime,
              step: data.step,
              status: data.status,
              message: data.message,
              elapsed: data.elapsed,
            },
          ]);

          if (data.step === "complete" || data.status === "error") {
            setIsRunning(false);
            if (timerRef.current) {
              clearInterval(timerRef.current);
              timerRef.current = null;
            }
            // Trigger stats reload to capture the finished run
            load();
          }
        }
      } catch (err) {
        console.error("Error parsing dashboard websocket message", err);
      }
    };

    return () => {
      clearInterval(intervalId);
      ws.close();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [currentSessionId]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const accuracy = stats
    ? [
        { name: "Đúng", value: stats.liked || 0 },
        { name: "Chưa đánh giá", value: stats.unrated || 0 },
        { name: "Sai", value: stats.disliked || 0 },
      ]
    : [];

  const kpis = [
    { label: "Tổng câu hỏi", value: stats?.total_questions ?? 0 },
    { label: "Cache hit rate", value: `${((stats?.cache_hit_rate ?? 0) * 100).toFixed(1)}%` },
    { label: "Avg response time", value: `${(stats?.avg_response_time ?? 0).toFixed(2)}s` },
    { label: "Active sessions", value: stats?.active_sessions ?? 0 },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-900">Dashboard BkAI</h1>
          <p className="text-slate-600">Theo dõi hiệu năng hệ thống tư vấn tuyển sinh</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400 font-mono select-none">Session: {currentSessionId.slice(0, 8)}...</span>
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              healthy ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
            }`}
          >
            {healthy ? "Healthy" : "Offline"}
          </span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-sm text-slate-500">{kpi.label}</div>
            <div className="font-display text-3xl font-bold text-brand-700 mt-2">{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* Live System Logs Stream Console */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col">
        <div className="flex items-center justify-between mb-3.5">
          <div className="flex items-center gap-2">
            <div className="relative flex h-3 w-3">
              <span className={`absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75 ${isRunning ? "animate-ping" : ""}`} />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-500" />
            </div>
            <h2 className="font-display font-semibold text-slate-800">Tiến trình xử lý câu hỏi real-time</h2>
          </div>
          {isRunning && activeQuery && (
            <div className="flex items-center gap-4 text-xs font-mono text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-3.5 py-1">
              <span className="truncate max-w-xs font-medium">Q: "{activeQuery}"</span>
              <span className="font-semibold tabular-nums border-l border-indigo-200 pl-3">Thời gian: {activeTime.toFixed(1)}s</span>
            </div>
          )}
        </div>

        <div className="bg-slate-900 border border-slate-850 text-slate-100 rounded-xl font-mono text-[12px] overflow-hidden flex flex-col h-72">
          <div className="flex items-center justify-between bg-slate-950 px-4 py-2 border-b border-slate-800 text-[10px] text-slate-400 uppercase tracking-wider">
            <span>System Console Logs</span>
            <span>UTF-8</span>
          </div>
          <div className="flex-1 p-4 overflow-y-auto space-y-2 select-text scrollbar-thin scrollbar-thumb-slate-800">
            {logs.length === 0 ? (
              <div className="h-full flex items-center justify-center text-slate-500 text-xs italic">
                ⏳ Hệ thống đang chờ câu hỏi từ phiên làm việc của bạn...
              </div>
            ) : (
              logs.map((log, idx) => {
                const stepLabel = STEP_TRANSLATIONS[log.step] || log.step;
                let statusColor = "text-sky-400";
                if (log.status === "done") statusColor = "text-emerald-400";
                if (log.status === "error") statusColor = "text-rose-400";

                return (
                  <div key={idx} className="leading-relaxed hover:bg-slate-800/40 px-1 py-0.5 rounded transition-colors">
                    <span className="text-slate-500 select-none mr-2">[{log.time}]</span>
                    <span className={`font-semibold mr-1.5 ${statusColor}`}>
                      [{stepLabel}]
                    </span>
                    <span className="text-slate-300">{log.message}</span>
                    {log.elapsed !== undefined && (
                      <span className="text-slate-500 text-[11px] ml-2">({log.elapsed}s)</span>
                    )}
                  </div>
                );
              })
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      </div>

      {/* Analytics Row */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Pie Chart: Độ chính xác */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm h-80">
          <h2 className="font-display font-semibold mb-4 text-slate-800">Độ chính xác (Đánh giá)</h2>
          <div className="h-[80%] flex items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={accuracy} dataKey="value" nameKey="name" outerRadius={90} label>
                  {accuracy.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-col gap-2.5 text-xs text-slate-600 font-medium pl-4 border-l border-slate-100">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-[#10b981]" />
                <span>Đúng: {stats?.liked || 0}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-[#f59e0b]" />
                <span>Chưa đánh giá: {stats?.unrated || 0}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-[#ef4444]" />
                <span>Sai: {stats?.disliked || 0}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Line Chart: Xu hướng */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm h-80">
          <h2 className="font-display font-semibold mb-4 text-slate-800">Xu hướng câu hỏi (24h)</h2>
          <ResponsiveContainer width="100%" height="85%">
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="timestamp" hide />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="total" stroke="#3b82f6" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bar Chart: Response times */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm h-72">
        <h2 className="font-display font-semibold mb-4 text-slate-800">Thời gian phản hồi gần đây</h2>
        <ResponsiveContainer width="100%" height="80%">
          <BarChart data={history.slice(-12)}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="timestamp" hide />
            <YAxis />
            <Tooltip />
            <Bar dataKey="avg_response_time" fill="#3b82f6" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
