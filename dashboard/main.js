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
const API_BASE = "http://localhost:8000";
const ENDPOINTS = {
  stats: `${API_BASE}/api/stats`,
  health: `${API_BASE}/api/health`,
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
    setUnhealthy("Không thể kết nối backend");
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
    setUnhealthy("Lỗi kết nối API");
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
  elements.lastUpdated.textContent = now.toLocaleTimeString("vi-VN", {
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
    const t = new Date(lastError.timestamp * 1000).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
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

function flashValue(el) {
  el.classList.remove("updated");
  // Force reflow
  void el.offsetWidth;
  el.classList.add("updated");
}

// ═══════════════════════════════════════════
// Charts
// ═══════════════════════════════════════════
function initCharts() {
  // Global Chart.js defaults
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
      labels: ["Hài lòng", "Chưa hài lòng", "Chưa đánh giá"],
      datasets: [
        {
          data: [0, 0, 0],
          backgroundColor: [
            "rgba(52, 211, 153, 0.8)",
            "rgba(248, 113, 113, 0.8)",
            "rgba(251, 191, 36, 0.6)",
          ],
          borderColor: [
            "rgba(52, 211, 153, 1)",
            "rgba(248, 113, 113, 1)",
            "rgba(251, 191, 36, 1)",
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
      labels: ["TB Phản hồi", "TB Build Answer"],
      datasets: [
        {
          label: "Thời gian (giây)",
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
          label: "Tổng câu hỏi",
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
          label: "Hài lòng",
          data: [],
          borderColor: "rgba(52, 211, 153, 1)",
          backgroundColor: "rgba(52, 211, 153, 0.05)",
          fill: true,
          tension: 0.4,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointBackgroundColor: "rgba(52, 211, 153, 1)",
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
    return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
  elements.feedCount.textContent = `${questions.length} câu hỏi`;

  if (questions.length === 0) {
    elements.feedList.innerHTML = `
      <div class="feed-empty">
        <span class="feed-empty-icon">📭</span>
        <p>Chưa có câu hỏi nào</p>
      </div>
    `;
    return;
  }

  elements.feedList.innerHTML = questions
    .map((q, i) => {
      const time = q.timestamp
        ? new Date(q.timestamp * 1000).toLocaleTimeString("vi-VN", {
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
      return '<span class="feed-meta-chip liked">👍 Liked</span>';
    case "dislike":
      return '<span class="feed-meta-chip disliked">👎 Disliked</span>';
    default:
      return '<span class="feed-meta-chip unrated">⏳ Unrated</span>';
  }
}

// ═══════════════════════════════════════════
// Pipeline Visualization
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
    statuses.nodeRewriteStatus.textContent = "Bỏ qua";
    nodes.nodeRetrieval.classList.add("skip");
    statuses.nodeRetrievalStatus.textContent = "Bỏ qua";
    nodes.nodeGenerate.classList.add("skip");
    statuses.nodeGenerateStatus.textContent = "Bỏ qua";
    nodes.nodeReflect.classList.add("skip");
    statuses.nodeReflectStatus.textContent = "Bỏ qua";
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
    ? new Date(q.timestamp * 1000).toLocaleString("vi-VN")
    : "N/A";

  const feedbackLabel =
    q.feedback === "like"
      ? "👍 Hài lòng"
      : q.feedback === "dislike"
      ? "👎 Chưa hài lòng"
      : "⏳ Chưa đánh giá";

  const trace = q.trace || {};
  const rewritten = trace.rewritten_queries && trace.rewritten_queries.length > 0 
    ? trace.rewritten_queries.map(rq => `<li>${escapeHtml(rq)}</li>`).join('')
    : "Không có";
    
  const sources = trace.sources && trace.sources.length > 0
    ? trace.sources.map(s => `<div class="source-chip">📄 ${escapeHtml(s)}</div>`).join('')
    : "Không sử dụng tài liệu";
    
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
        <h4 class="trace-title">📝 Câu hỏi gốc</h4>
        <div class="trace-box">${escapeHtml(q.query || "N/A")}</div>
      </div>
      
      <div class="trace-section">
        <h4 class="trace-title">✏️ Rewritten Queries (Hops: ${trace.retrieval_hops || 0})</h4>
        <ul class="trace-list">${rewritten}</ul>
      </div>
      
      <div class="trace-section">
        <h4 class="trace-title">🔍 Tài liệu (Sources)</h4>
        <div class="source-container">${sources}</div>
      </div>
      
      <div class="trace-section">
        <h4 class="trace-title">⏱ Step Timings</h4>
        ${timingsHtml}
      </div>

      <div class="trace-section">
        <h4 class="trace-title">💬 Trả lời</h4>
        <div class="trace-box">${escapeHtml((q.answer || "N/A").substring(0, 300))}${(q.answer || "").length > 300 ? "..." : ""}</div>
      </div>
      
      <div class="trace-meta">
        <span class="meta-chip">⚡ Cache: ${q.cached ? "Hit" : "Miss"}</span>
        <span class="meta-chip">⭐ Đánh giá: ${feedbackLabel}</span>
        <span class="meta-chip">🕐 ${time}</span>
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
