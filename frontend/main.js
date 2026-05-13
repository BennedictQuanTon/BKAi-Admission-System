/**
 * BKAi Chat UI — Main Application Logic
 *
 * Handles WebSocket communication, message rendering,
 * feedback system, and UI state management.
 */

const API_BASE = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/chat";

// ── State ──
let sessionId = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
let isProcessing = false;
let ws = null;

// ── DOM Elements ──
const messagesScroll = document.getElementById("messagesScroll");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const newChatBtn = document.getElementById("newChatBtn");
const welcomeScreen = document.getElementById("welcomeScreen");
const charCount = document.getElementById("charCount");
const statResponseTime = document.getElementById("statResponseTime");
const menuBtn = document.getElementById("menuBtn");
const sidebar = document.getElementById("sidebar");

// ── Initialize ──
function init() {
  setupEventListeners();
  connectWebSocket();
  chatInput.focus();
}

// ── Event Listeners ──
function setupEventListeners() {
  // Send button
  sendBtn.addEventListener("click", handleSend);

  // Enter to send (Shift+Enter for newline)
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  });

  // Auto-resize textarea + char count
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
    charCount.textContent = chatInput.value.length;
    sendBtn.disabled = chatInput.value.trim().length === 0 || isProcessing;
  });

  // New chat
  newChatBtn.addEventListener("click", startNewChat);

  // Suggestion buttons
  document.querySelectorAll("[data-query]").forEach((btn) => {
    btn.addEventListener("click", () => {
      chatInput.value = btn.dataset.query;
      chatInput.dispatchEvent(new Event("input"));
      handleSend();
    });
  });

  // Mobile menu
  menuBtn.addEventListener("click", () => {
    sidebar.classList.toggle("open");
  });

  // Close sidebar on message area click (mobile)
  document.querySelector(".chat-main").addEventListener("click", () => {
    sidebar.classList.remove("open");
  });
}

// ── WebSocket Connection ──
function connectWebSocket() {
  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => console.log("[WS] Connected");

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleWSMessage(data);
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected, falling back to REST");
      ws = null;
    };

    ws.onerror = () => {
      console.log("[WS] Error, using REST API");
      ws = null;
    };
  } catch {
    ws = null;
  }
}

// ── Handle WebSocket Messages ──
function handleWSMessage(data) {
  switch (data.type) {
    case "status":
      // Update typing indicator text
      break;

    case "done":
      removeTypingIndicator();
      addAssistantMessage(data.answer, data.metadata || {});
      isProcessing = false;
      sendBtn.disabled = chatInput.value.trim().length === 0;
      break;

    case "error":
      removeTypingIndicator();
      addAssistantMessage(data.message || "Có lỗi xảy ra.", { error: true });
      isProcessing = false;
      sendBtn.disabled = false;
      break;
  }
}

// ── Send Message ──
async function handleSend() {
  const query = chatInput.value.trim();
  if (!query || isProcessing) return;

  isProcessing = true;
  sendBtn.disabled = true;

  // Hide welcome screen
  if (welcomeScreen) {
    welcomeScreen.style.display = "none";
  }

  // Add user message
  addUserMessage(query);

  // Clear input
  chatInput.value = "";
  chatInput.style.height = "auto";
  charCount.textContent = "0";

  // Show typing indicator
  showTypingIndicator();

  // Send via WebSocket or fallback to REST
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ query, session_id: sessionId }));
  } else {
    await sendREST(query);
  }
}

// ── REST API Fallback ──
async function sendREST(query) {
  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, session_id: sessionId }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    removeTypingIndicator();
    addAssistantMessage(data.answer, {
      cached: data.cached,
      confidence: data.confidence,
      sources: data.sources,
      timings: data.timings,
      retrieval_hops: data.retrieval_hops,
    });
  } catch (err) {
    removeTypingIndicator();
    addAssistantMessage(
      "Xin lỗi, không thể kết nối đến server. Vui lòng kiểm tra backend đang chạy.",
      { error: true }
    );
  }

  isProcessing = false;
  sendBtn.disabled = chatInput.value.trim().length === 0;
}

// ── Message Rendering ──
function addUserMessage(text) {
  const html = `
    <div class="message user">
      <div class="message-avatar">👤</div>
      <div class="message-content">
        <div class="message-bubble">${escapeHtml(text)}</div>
      </div>
    </div>
  `;
  messagesScroll.insertAdjacentHTML("beforeend", html);
  scrollToBottom();
}

function addAssistantMessage(text, metadata = {}) {
  const msgId = `msg_${Date.now()}`;
  const formattedText = formatMarkdown(text);

  // Build meta items
  let metaHtml = "";
  if (metadata.timings?.total) {
    const t = metadata.timings.total;
    metaHtml += `<span class="meta-item">⏱ ${t.toFixed(1)}s</span>`;
    statResponseTime.textContent = `⏱ ${t.toFixed(1)}s`;
  }
  if (metadata.cached) {
    metaHtml += `<span class="meta-item" style="color: var(--success)">⚡ Cache</span>`;
    statResponseTime.textContent = `⚡ Cache`;
  }
  if (metadata.confidence) {
    const pct = (metadata.confidence * 100).toFixed(0);
    metaHtml += `<span class="meta-item">🎯 ${pct}%</span>`;
  }

  const html = `
    <div class="message assistant" id="${msgId}">
      <div class="message-avatar">BK</div>
      <div class="message-content">
        <div class="message-bubble">${formattedText}</div>
        <div class="message-meta">
          ${metaHtml}
          <div class="feedback-btns">
            <button class="feedback-btn like" onclick="sendFeedback('${msgId}', 'like')" title="Hữu ích">👍</button>
            <button class="feedback-btn dislike" onclick="sendFeedback('${msgId}', 'dislike')" title="Chưa chính xác">👎</button>
          </div>
        </div>
      </div>
    </div>
  `;
  messagesScroll.insertAdjacentHTML("beforeend", html);

  // Store query for feedback
  const msgEl = document.getElementById(msgId);
  msgEl.dataset.query = text;

  scrollToBottom();
}

// ── Typing Indicator ──
function showTypingIndicator() {
  const html = `
    <div class="message assistant" id="typingIndicator">
      <div class="message-avatar">BK</div>
      <div class="message-content">
        <div class="typing-indicator">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>
    </div>
  `;
  messagesScroll.insertAdjacentHTML("beforeend", html);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

// ── Feedback ──
window.sendFeedback = async function (msgId, feedback) {
  const msgEl = document.getElementById(msgId);
  if (!msgEl) return;

  // Find the user message above
  const messages = document.querySelectorAll(".message.user");
  const lastUserMsg = messages[messages.length - 1];
  const query = lastUserMsg?.querySelector(".message-bubble")?.textContent || "";

  // Visual feedback
  const btns = msgEl.querySelectorAll(".feedback-btn");
  btns.forEach((b) => b.classList.remove("active"));
  msgEl.querySelector(`.feedback-btn.${feedback}`).classList.add("active");

  // Send to API
  try {
    await fetch(`${API_BASE}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        answer: msgEl.querySelector(".message-bubble").textContent,
        feedback,
        session_id: sessionId,
      }),
    });
  } catch (err) {
    console.error("Feedback error:", err);
  }
};

// ── New Chat ──
function startNewChat() {
  sessionId = `s_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  messagesScroll.innerHTML = "";

  // Re-add welcome screen
  messagesScroll.innerHTML = `
    <div class="welcome-screen" id="welcomeScreen">
      <div class="welcome-icon">🎓</div>
      <h2 class="welcome-title">Xin chào! Tôi là <span class="accent">BKAi</span></h2>
      <p class="welcome-desc">Trợ lý tư vấn tuyển sinh thông minh của Trường Đại học Bách khoa - ĐHQG-HCM.</p>
      <div class="welcome-chips">
        <button class="welcome-chip" data-query="Trường Bách khoa có những ngành nào?">Các ngành đào tạo</button>
        <button class="welcome-chip" data-query="Phương thức xét tuyển năm 2026?">Phương thức xét tuyển</button>
        <button class="welcome-chip" data-query="Học bổng và hỗ trợ tài chính?">Học bổng & tài chính</button>
      </div>
    </div>
  `;

  // Re-attach suggestion listeners
  document.querySelectorAll("[data-query]").forEach((btn) => {
    btn.addEventListener("click", () => {
      chatInput.value = btn.dataset.query;
      chatInput.dispatchEvent(new Event("input"));
      handleSend();
    });
  });

  statResponseTime.textContent = "⏱ --";
  chatInput.focus();
}

// ── Utilities ──
function scrollToBottom() {
  requestAnimationFrame(() => {
    messagesScroll.scrollTop = messagesScroll.scrollHeight;
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatMarkdown(text) {
  return text
    // Bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Line breaks
    .replace(/\n/g, "<br>")
    // Bullet points
    .replace(
      /^- (.+)/gm,
      '<span style="display:flex;gap:8px;margin:2px 0"><span style="color:var(--accent-light)">•</span><span>$1</span></span>'
    );
}

// ── Start ──
init();
