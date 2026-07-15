const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export { API_BASE, WS_BASE };

const SESSION_KEY = "bkai_session_id";

/** Session-scoped id (tab lifetime). Cleared on New chat / explicit reset. */
export function getSessionId(): string {
  let sid = sessionStorage.getItem(SESSION_KEY);
  if (!sid) {
    sid = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}

export function newSessionId(): string {
  const sid = crypto.randomUUID();
  sessionStorage.setItem(SESSION_KEY, sid);
  return sid;
}

export async function clearServerSession(sessionId: string) {
  try {
    await fetch(`${API_BASE}/api/session/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch {
    // best-effort
  }
}

export async function fetchLiveKitToken(sessionId: string) {
  const res = await fetch(`${API_BASE}/api/livekit/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  if (!res.ok) {
    throw new Error("LiveKit token unavailable");
  }
  return res.json() as Promise<{
    token: string;
    url: string;
    room_name: string;
    session_id: string;
  }>;
}

export type ChatMetadata = {
  cached?: boolean;
  confidence?: number;
  sources?: string[];
  timings?: Record<string, number | boolean>;
  response_time?: number;
  retrieval_hops?: number;
  guardrail?: boolean;
  counselor_action?: string;
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
