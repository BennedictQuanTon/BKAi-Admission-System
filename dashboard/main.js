/**
 * BKAi Monitoring Dashboard — Main Application Logic
 *
 * Real-time stats polling, Chart.js visualizations,
 * recent questions feed, and agent pipeline visualization.
 */

import Chart from "chart.js/auto";

// ═══════════════════════════════════════════
// Configuration
// ═══════════════════════════════════════════
const API_BASE = window.location.origin.includes("localhost") 
  ? "http://localhost:8000" 
  : window.location.origin;
const WS_BASE = API_BASE.replace(/^http/, "ws");

const ENDPOINTS = {
  stats: `${API_BASE}/api/stats`,
  health: `${API_BASE}/api/health`,
  evaluate: `${API_BASE}/api/admin/evaluate`,
};

const STEP_TRANSLATIONS = {
  start: "Initialization",
  guardrail: "Guardrails (Safety Check)",
  cache: "Semantic Cache Check",
  query_rewrite: "Query Rewrite (Optimization)",
  retrieve: "Retrieval (RAG Docs Search)",
  evaluate_results: "Evaluation (RAG Quality)",
  generate: "Generation (LLM Output)",
  self_reflect: "Self-Reflection (Quality Verification)",
  complete: "Resolution Completed",
  error: "System Exception",
};

// ═══════════════════════════════════════════
// State
// ═══════════════════════════════════════════
let refreshTimer = null;
let currentStats = null;
let statsHistory = []; // Track stats over time for trend chart
let selectedQuestion = null;

// Chart instances
let satisfactionChart = null;
let timingsChart = null;
let trendChart = null;

// ═══════════════════════════════════════════
// DOM References
// ═══════════════════════════════════════════
const elements = {
  // Health
  healthBadge: document.getElementById("healthBadge"),
  healthText: document.querySelector(".health-text"),

  // KPI values
  totalQuestions: document.getElementById("totalQuestions"),
  likedCount: document.getElementById("likedCount"),
  dislikedCount: document.getElementById("dislikedCount"),
  unratedCount: document.getElementById("unratedCount"),
  avgResponseTime: document.getElementById("avgResponseTime"),
  cacheHitRate: document.getElementById("cacheHitRate"),
  likedRate: document.getElementById("likedRate"),
  dislikedRate: document.getElementById("dislikedRate"),
  errorCount: document.getElementById("errorCount"),
  lastErrorTime: document.getElementById("lastErrorTime"),
  activeSessions: document.getElementById("activeSessions"),

  // Controls
  refreshBtn: document.getElementById("refreshBtn"),
  refreshInterval: document.getElementById("refreshInterval"),
  lastUpdated: document.getElementById("lastUpdated"),

  // Feed
  feedList: document.getElementById("feedList"),
  feedCount: document.getElementById("feedCount"),

  // Pipeline
  pipelineDetail: document.getElementById("pipelineDetail"),
};

// ═══════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════
function init() {
  setupEventListeners();
  initCharts();
  checkHealth();
  fetchStats();
  fetchHistory(currentHistoryHours);
  startAutoRefresh();
  setupWebSocket();
}

let currentHistoryHours = 24;

async function fetchHistory(hours) {
  try {
    const res = await fetch(`${API_BASE}/api/stats/history?hours=${hours}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    statsHistory = (data.history || []).map(item => {
        const ts = item.timestamp > 1e11 ? item.timestamp : item.timestamp * 1000;
        return {
            ...item,
            timestamp: ts
        };
    });
    
    if (currentStats) {
      updateCharts(currentStats);
    }
  } catch (err) {
    console.error("[Dashboard] Fetch history error:", err);
  }
}

function setupEventListeners() {
  elements.refreshBtn.addEventListener("click", () => {
    elements.refreshBtn.classList.add("spinning");
    fetchStats().then(() => {
      setTimeout(() => elements.refreshBtn.classList.remove("spinning"), 600);
    });
  });

  elements.refreshInterval.addEventListener("change", () => {
    startAutoRefresh();
  });

  document.querySelectorAll('.time-chip').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.time-chip').forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      const hours = parseInt(e.target.dataset.hours, 10);
      currentHistoryHours = hours;
      fetchHistory(hours);
    });
  });
}

// ═══════════════════════════════════════════
// Health Check
// ═══════════════════════════════════════════
async function checkHealth() {
  try {
    const res = await fetch(ENDPOINTS.health, { signal: AbortSignal.timeout(5000) });
    const data = await res.json();

    if (data.status === "healthy") {
      elements.healthBadge.className = "health-badge healthy";
      elements.healthText.textContent = `${data.service} v${data.version} — Online`;
    } else {
      setUnhealthy("Unhealthy");
    }
  } catch {
    setUnhealthy("Cannot connect to backend");
  }
}

function setUnhealthy(msg) {
  elements.healthBadge.className = "health-badge unhealthy";
  elements.healthText.textContent = msg;
}

// ═══════════════════════════════════════════
// Fetch Stats
// ═══════════════════════════════════════════
async function fetchStats() {
  try {
    const res = await fetch(ENDPOINTS.stats, { signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    currentStats = data;

    // Track history for trend chart (max 30 data points)
    statsHistory.push({
      timestamp: Date.now(),
      total: data.total_questions,
      liked: data.liked,
      disliked: data.disliked,
    });
    if (statsHistory.length > 30) statsHistory.shift();

    updateKPIs(data);
    updateCharts(data);
    updateFeed(data.recent_questions || []);
    updateLastUpdated();

    // Also refresh health
    checkHealth();
  } catch (err) {
    console.error("[Dashboard] Fetch stats error:", err);
    setUnhealthy("API Connection Error");
  }
}

// ═══════════════════════════════════════════
// Auto Refresh
// ═══════════════════════════════════════════
function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);

  const interval = parseInt(elements.refreshInterval.value, 10);
  if (interval > 0) {
    refreshTimer = setInterval(fetchStats, interval);
  }
}

function updateLastUpdated() {
  const now = new Date();
  elements.lastUpdated.textContent = now.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

// ═══════════════════════════════════════════
// KPI Updates
// ═══════════════════════════════════════════
function updateKPIs(data) {
  animateValue(elements.totalQuestions, data.total_questions);
  animateValue(elements.likedCount, data.liked);
  animateValue(elements.dislikedCount, data.disliked);
  animateValue(elements.unratedCount, data.unrated);

  // Average response time
  const avgTime = data.avg_response_time || 0;
  elements.avgResponseTime.textContent =
    avgTime > 60 ? `${(avgTime / 60).toFixed(1)}m` : `${avgTime.toFixed(1)}s`;
  flashValue(elements.avgResponseTime);

  // Cache hit rate
  const cacheRate = (data.cache_hit_rate || 0) * 100;
  elements.cacheHitRate.textContent = `${cacheRate.toFixed(1)}%`;
  flashValue(elements.cacheHitRate);

  // Satisfaction rates
  const total = data.total_questions || 1;
  elements.likedRate.textContent = `${((data.liked / total) * 100).toFixed(0)}%`;
  elements.dislikedRate.textContent = `${((data.disliked / total) * 100).toFixed(0)}%`;

  animateValue(elements.errorCount, data.error_count || 0);
  animateValue(elements.activeSessions, data.active_sessions || 0);
  
  if (data.recent_errors && data.recent_errors.length > 0) {
    const lastError = data.recent_errors[0];
    const t = new Date(lastError.timestamp * 1000).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    elements.lastErrorTime.textContent = t;
  } else {
    elements.lastErrorTime.textContent = "--";
  }
}

function animateValue(el, newValue) {
  const current = parseInt(el.textContent, 10) || 0;
  if (current !== newValue) {
    el.textContent = newValue;
    flashValue(el);
  }
}

// WebSocket setup for streaming progress logs
function setupWebSocket() {
  const wsUrl = `${WS_BASE}/ws/dashboard`;
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "progress") {
        appendLiveLog(data);
      }
    } catch (err) {
      console.error("[Dashboard WS] Error parsing message:", err);
    }
  };

  ws.onclose = () => {
    console.log("[Dashboard WS] Connection closed. Reconnecting in 3 seconds...");
    setTimeout(setupWebSocket, 3000);
  };

  ws.onerror = (err) => {
    console.error("[Dashboard WS] WebSocket error:", err);
  };
}

function appendLiveLog(data) {
  const consoleEl = document.getElementById("liveLogsConsole");
  if (!consoleEl) return;

  const placeholder = consoleEl.querySelector(".placeholder");
  if (placeholder) {
    placeholder.remove();
  }

  const logTime = new Date(data.timestamp * 1000).toLocaleTimeString("en-US");
  const stepLabel = STEP_TRANSLATIONS[data.step] || data.step;
  let statusClass = "step-running";
  if (data.status === "done") statusClass = "step-done";
  if (data.status === "error") statusClass = "step-error";

  const line = document.createElement("div");
  line.className = "console-line";
  
  const elapsedStr = data.elapsed !== undefined ? ` (${data.elapsed}s)` : "";
  const sessionStr = `<span class="console-session">[Session: ${data.session_id.slice(0, 6)}...]</span>`;

  line.innerHTML = `
    <span class="console-time">[${logTime}]</span>
    ${sessionStr}
    <span class="console-step ${statusClass}">[${stepLabel}]</span>
    <span class="console-msg">${escapeHtml(data.message)}</span>
    <span class="console-elapsed">${elapsedStr}</span>
  `;

  consoleEl.appendChild(line);
  consoleEl.scrollTop = consoleEl.scrollHeight;

  while (consoleEl.children.length > 100) {
    consoleEl.removeChild(consoleEl.firstChild);
  }
}

function flashValue(el) {
  el.classList.remove("updated");
  void el.offsetWidth;
  el.classList.add("updated");
}

// ═══════════════════════════════════════════
// Charts
// ═══════════════════════════════════════════
function initCharts() {
  Chart.defaults.color = "#9898b0";
  Chart.defaults.borderColor = "rgba(255, 255, 255, 0.06)";
  Chart.defaults.font.family = "'Inter', sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyleWidth = 12;

  initSatisfactionChart();
  initTimingsChart();
  initTrendChart();
}

function initSatisfactionChart() {
  const ctx = document.getElementById("satisfactionChart").getContext("2d");
  satisfactionChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Correct", "Incorrect", "Unrated"],
      datasets: [
        {
          data: [0, 0, 0],
          backgroundColor: [
            "rgba(16, 185, 129, 0.8)", // Emerald green
            "rgba(239, 68, 68, 0.8)",   // Rose red
            "rgba(245, 158, 11, 0.6)",  // Amber yellow
          ],
          borderColor: [
            "rgba(16, 185, 129, 1)",
            "rgba(239, 68, 68, 1)",
            "rgba(245, 158, 11, 1)",
          ],
          borderWidth: 2,
          hoverOffset: 8,
          spacing: 3,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "65%",
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            padding: 16,
            usePointStyle: true,
            pointStyleWidth: 10,
          },
        },
        tooltip: {
          backgroundColor: "rgba(18, 18, 26, 0.95)",
          borderColor: "rgba(255, 255, 255, 0.1)",
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
          titleFont: { weight: 600 },
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct = total ? ((ctx.raw / total) * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${ctx.raw} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

function initTimingsChart() {
  const ctx = document.getElementById("timingsChart").getContext("2d");
  timingsChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: ["Avg Response", "Avg Build Answer"],
      datasets: [
        {
          label: "Time (seconds)",
          data: [0, 0],
          backgroundColor: [
            "rgba(99, 102, 241, 0.6)",
            "rgba(139, 92, 246, 0.6)",
          ],
          borderColor: [
            "rgba(99, 102, 241, 1)",
            "rgba(139, 92, 246, 1)",
          ],
          borderWidth: 2,
          borderRadius: 8,
          borderSkipped: false,
          barPercentage: 0.5,
          categoryPercentage: 0.6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            callback: (v) => `${v}s`,
          },
        },
        y: {
          grid: { display: false },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(18, 18, 26, 0.95)",
          borderColor: "rgba(255, 255, 255, 0.1)",
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
          callbacks: {
            label: (ctx) => ` ${ctx.raw.toFixed(2)}s`,
          },
        },
      },
    },
  });
}

function initTrendChart() {
  const ctx = document.getElementById("trendChart").getContext("2d");
  trendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Total Questions",
          data: [],
          borderColor: "rgba(96, 165, 250, 1)",
          backgroundColor: "rgba(96, 165, 250, 0.1)",
          fill: true,
          tension: 0.4,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: "rgba(96, 165, 250, 1)",
          pointBorderColor: "#12121a",
          pointBorderWidth: 2,
          borderWidth: 2,
        },
        {
          label: "Correct Answers",
          data: [],
          borderColor: "rgba(16, 185, 129, 1)",
          backgroundColor: "rgba(16, 185, 129, 0.05)",
          fill: true,
          tension: 0.4,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointBackgroundColor: "rgba(16, 185, 129, 1)",
          pointBorderColor: "#12121a",
          pointBorderWidth: 2,
          borderWidth: 1.5,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            stepSize: 1,
            precision: 0,
          },
        },
      },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: {
            padding: 12,
            usePointStyle: true,
          },
        },
        tooltip: {
          backgroundColor: "rgba(18, 18, 26, 0.95)",
          borderColor: "rgba(255, 255, 255, 0.1)",
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
        },
      },
    },
  });
}

function updateCharts(data) {
  // Satisfaction doughnut
  satisfactionChart.data.datasets[0].data = [
    data.liked || 0,
    data.disliked || 0,
    data.unrated || 0,
  ];
  satisfactionChart.update("none");

  // Timings bar
  timingsChart.data.datasets[0].data = [
    data.avg_response_time || 0,
    data.avg_build_time || 0,
  ];
  timingsChart.update("none");

  // Trend line
  const labels = statsHistory.map((s) => {
    const d = new Date(s.timestamp);
    return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  });

  trendChart.data.labels = labels;
  trendChart.data.datasets[0].data = statsHistory.map((s) => s.total);
  trendChart.data.datasets[1].data = statsHistory.map((s) => s.liked);
  trendChart.update("none");
}

// ═══════════════════════════════════════════
// Recent Questions Feed
// ═══════════════════════════════════════════
function updateFeed(questions) {
  elements.feedCount.textContent = `${questions.length} questions`;

  if (questions.length === 0) {
    elements.feedList.innerHTML = `
      <div class="feed-empty">
        <span class="feed-empty-icon">📭</span>
        <p>No questions yet</p>
      </div>
    `;
    return;
  }

  elements.feedList.innerHTML = questions
    .map((q, i) => {
      const time = q.timestamp
        ? new Date(q.timestamp * 1000).toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
          })
        : "--:--";

      const feedbackChip = getFeedbackChip(q.feedback);
      const cachedChip = q.cached
        ? '<span class="feed-meta-chip cached">⚡ Cache</span>'
        : "";

      const responseTime = q.response_time ? `${q.response_time.toFixed(1)}s` : "--";
      const isSelected = selectedQuestion === i;

      return `
        <div class="feed-item ${isSelected ? "selected" : ""}"
             data-index="${i}"
             onclick="window.selectQuestion(${i})"
             style="animation-delay: ${i * 0.05}s">
          <div class="feed-item-query" title="${escapeHtml(q.query || "")}">${escapeHtml(q.query || "N/A")}</div>
          <div class="feed-item-meta">
            <span>🕐 ${time}</span>
            <span>⏱ ${responseTime}</span>
            ${feedbackChip}
            ${cachedChip}
          </div>
        </div>
      `;
    })
    .join("");
}

function getFeedbackChip(feedback) {
  switch (feedback) {
    case "like":
      return '<span class="feed-meta-chip liked">👍 Correct</span>';
    case "dislike":
      return '<span class="feed-meta-chip disliked">👎 Incorrect</span>';
    default:
      return '<span class="feed-meta-chip unrated">⏳ Unrated</span>';
  }
}

// ═══════════════════════════════════════════
// Pipeline Visualization & Evaluation
// ═══════════════════════════════════════════
window.selectQuestion = function (index) {
  if (!currentStats || !currentStats.recent_questions) return;

  const q = currentStats.recent_questions[index];
  if (!q) return;

  selectedQuestion = index;

  // Highlight selected feed item
  document.querySelectorAll(".feed-item").forEach((el, i) => {
    el.classList.toggle("selected", i === index);
  });

  // Update pipeline nodes
  updatePipelineNodes(q);

  // Show detail
  showPipelineDetail(q);
};

window.evaluateAnswer = async function (questionId, feedback) {
  try {
    const res = await fetch(ENDPOINTS.evaluate, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        question_id: questionId,
        feedback: feedback,
      }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    // Refresh dashboard stats
    await fetchStats();
    
    // Re-select current question to update detail details view
    if (selectedQuestion !== null) {
      window.selectQuestion(selectedQuestion);
    }
  } catch (err) {
    console.error("[Dashboard] Evaluation error:", err);
    alert("Failed to save evaluation. Please try again.");
  }
};

function updatePipelineNodes(q) {
  const nodes = {
    nodeCache: document.getElementById("nodeCache"),
    nodeRewrite: document.getElementById("nodeRewrite"),
    nodeRetrieval: document.getElementById("nodeRetrieval"),
    nodeGenerate: document.getElementById("nodeGenerate"),
    nodeReflect: document.getElementById("nodeReflect"),
  };

  const statuses = {
    nodeCacheStatus: document.getElementById("nodeCacheStatus"),
    nodeRewriteStatus: document.getElementById("nodeRewriteStatus"),
    nodeRetrievalStatus: document.getElementById("nodeRetrievalStatus"),
    nodeGenerateStatus: document.getElementById("nodeGenerateStatus"),
    nodeReflectStatus: document.getElementById("nodeReflectStatus"),
  };

  // Reset all nodes
  Object.values(nodes).forEach((n) => {
    n.className = "pipeline-node";
  });

  if (q.cached) {
    // Cache hit — only cache node is active, rest are skipped
    nodes.nodeCache.classList.add("done");
    statuses.nodeCacheStatus.textContent = "HIT ⚡";
    statuses.nodeCacheStatus.style.color = "#22d3ee";

    nodes.nodeRewrite.classList.add("skip");
    statuses.nodeRewriteStatus.textContent = "Skipped";
    nodes.nodeRetrieval.classList.add("skip");
    statuses.nodeRetrievalStatus.textContent = "Skipped";
    nodes.nodeGenerate.classList.add("skip");
    statuses.nodeGenerateStatus.textContent = "Skipped";
    nodes.nodeReflect.classList.add("skip");
    statuses.nodeReflectStatus.textContent = "Skipped";
  } else {
    // Full pipeline
    nodes.nodeCache.classList.add("done");
    statuses.nodeCacheStatus.textContent = "MISS";
    statuses.nodeCacheStatus.style.color = "var(--warning)";

    nodes.nodeRewrite.classList.add("done");
    statuses.nodeRewriteStatus.textContent = "✓";
    statuses.nodeRewriteStatus.style.color = "var(--success)";

    nodes.nodeRetrieval.classList.add("done");
    statuses.nodeRetrievalStatus.textContent = "✓";
    statuses.nodeRetrievalStatus.style.color = "var(--success)";

    nodes.nodeGenerate.classList.add("done");
    statuses.nodeGenerateStatus.textContent = "✓";
    statuses.nodeGenerateStatus.style.color = "var(--success)";

    nodes.nodeReflect.classList.add("done");
    statuses.nodeReflectStatus.textContent = "✓";
    statuses.nodeReflectStatus.style.color = "var(--success)";
  }
}

function showPipelineDetail(q) {
  const time = q.timestamp
    ? new Date(q.timestamp * 1000).toLocaleString("en-US")
    : "N/A";

  const feedbackLabel =
    q.feedback === "like"
      ? "👍 Correct"
      : q.feedback === "dislike"
      ? "👎 Incorrect"
      : "⏳ Unrated";

  const trace = q.trace || {};
  const rewritten = trace.rewritten_queries && trace.rewritten_queries.length > 0 
    ? trace.rewritten_queries.map(rq => `<li>${escapeHtml(rq)}</li>`).join('')
    : "None";
    
  const sources = trace.sources && trace.sources.length > 0
    ? trace.sources.map(s => `<div class="source-chip">📄 ${escapeHtml(s)}</div>`).join('')
    : "No document sources used";
    
  const timings = trace.step_timings || {};
  let timingsHtml = "";
  if (Object.keys(timings).length > 0) {
    timingsHtml = `<div class="timings-grid">`;
    for (const [step, t] of Object.entries(timings)) {
      timingsHtml += `<div class="timing-item"><span class="timing-label">${step}</span><span class="timing-val">${t.toFixed(2)}s</span></div>`;
    }
    timingsHtml += `</div>`;
  } else {
    timingsHtml = "N/A";
  }

  const confidence = trace.confidence || 0;
  const confColor = confidence > 0.8 ? "var(--success)" : (confidence > 0.5 ? "var(--warning)" : "var(--danger)");
  
  elements.pipelineDetail.innerHTML = `
    <div class="detail-content trace-panel">
      <div class="trace-header">
        <div class="trace-badge">Trace Data</div>
        <div class="confidence-bar-container">
          <span class="conf-label">Confidence: ${(confidence * 100).toFixed(0)}%</span>
          <div class="conf-bar-bg"><div class="conf-bar-fill" style="width: ${confidence * 100}%; background: ${confColor}"></div></div>
        </div>
      </div>
      
      <div class="trace-section">
        <h4 class="trace-title">Original Query</h4>
        <div class="trace-box">${escapeHtml(q.query || "N/A")}</div>
      </div>
      
      <div class="trace-section">
        <h4 class="trace-title">Rewritten Queries (Hops: ${trace.retrieval_hops || 0})</h4>
        <ul class="trace-list">${rewritten}</ul>
      </div>
      
      <div class="trace-section">
        <h4 class="trace-title">Sources</h4>
        <div class="source-container">${sources}</div>
      </div>
      
      <div class="trace-section">
        <h4 class="trace-title">Step Timings</h4>
        ${timingsHtml}
      </div>

      <div class="trace-section">
        <h4 class="trace-title">Generated Answer</h4>
        <div class="trace-box">${escapeHtml((q.answer || "N/A").substring(0, 300))}${(q.answer || "").length > 300 ? "..." : ""}</div>
      </div>
      
      <div class="trace-meta" style="margin-bottom: 12px;">
        <span class="meta-chip">⚡ Cache: ${q.cached ? "Hit" : "Miss"}</span>
        <span class="meta-chip">⭐ Evaluation: ${feedbackLabel}</span>
        <span class="meta-chip">🕐 ${time}</span>
      </div>

      <div class="evaluate-actions" style="margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border); display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">Evaluate Answer:</span>
        <button onclick="window.evaluateAnswer('${q.id}', 'like')" class="eval-btn eval-btn-like">
          ✓ Correct
        </button>
        <button onclick="window.evaluateAnswer('${q.id}', 'dislike')" class="eval-btn eval-btn-dislike">
          ✗ Incorrect
        </button>
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ═══════════════════════════════════════════
// Start
// ═══════════════════════════════════════════
init();
