import { useEffect, useState } from "react";
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
import { fetchHealth, fetchStats, fetchStatsHistory } from "../lib/api";

const COLORS = ["#1d4ed8", "#94a3b8", "#f87171"];

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [healthy, setHealthy] = useState(true);

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
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, []);

  const satisfaction = stats
    ? [
        { name: "Liked", value: stats.liked || 0 },
        { name: "Unrated", value: stats.unrated || 0 },
        { name: "Disliked", value: stats.disliked || 0 },
      ]
    : [];

  const kpis = [
    { label: "Tổng câu hỏi", value: stats?.total_questions ?? 0 },
    { label: "Cache hit", value: `${((stats?.cache_hit_rate ?? 0) * 100).toFixed(1)}%` },
    { label: "Avg response", value: `${((stats?.avg_response_time ?? 0)).toFixed(2)}s` },
    { label: "Active sessions", value: stats?.active_sessions ?? 0 },
  ];

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-slate-900">Dashboard BkAI</h1>
          <p className="text-slate-600">Theo dõi hiệu năng hệ thống tư vấn tuyển sinh</p>
        </div>
        <span
          className={`px-3 py-1 rounded-full text-sm font-medium ${
            healthy ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
          }`}
        >
          {healthy ? "Healthy" : "Offline"}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="text-sm text-slate-500">{kpi.label}</div>
            <div className="font-display text-3xl font-bold text-brand-700 mt-2">{kpi.value}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm h-80">
          <h2 className="font-display font-semibold mb-4">Mức độ hài lòng</h2>
          <ResponsiveContainer width="100%" height="85%">
            <PieChart>
              <Pie data={satisfaction} dataKey="value" nameKey="name" outerRadius={90} label>
                {satisfaction.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm h-80">
          <h2 className="font-display font-semibold mb-4">Xu hướng câu hỏi (24h)</h2>
          <ResponsiveContainer width="100%" height="85%">
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" hide />
              <YAxis />
              <Tooltip />
              <Line type="monotone" dataKey="total_questions" stroke="#1d4ed8" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm h-72">
        <h2 className="font-display font-semibold mb-4">Thời gian phản hồi gần đây</h2>
        <ResponsiveContainer width="100%" height="80%">
          <BarChart data={history.slice(-12)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" hide />
            <YAxis />
            <Tooltip />
            <Bar dataKey="avg_response_time" fill="#2563eb" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
