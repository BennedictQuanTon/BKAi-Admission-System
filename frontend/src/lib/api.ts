const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export { API_BASE, WS_BASE };

export type ChatMetadata = {
  cached?: boolean;
  confidence?: number;
  sources?: string[];
  timings?: Record<string, number | boolean>;
  response_time?: number;
  retrieval_hops?: number;
  guardrail?: boolean;
};

export async function sendFeedback(query: string, feedback: "like" | "dislike") {
  await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, feedback }),
  });
}

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/api/stats`);
  return res.json();
}

export async function fetchStatsHistory(hours = 24) {
  const res = await fetch(`${API_BASE}/api/stats/history?hours=${hours}`);
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  return res.json();
}
