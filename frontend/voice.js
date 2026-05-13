/**
 * BKAi Voice — Main Application Logic
 *
 * Features:
 *   - Browser microphone recording with MediaRecorder API
 *   - Voice Activity Detection (VAD) — auto-stop on silence
 *   - Real-time waveform visualizer via Web Audio API
 *   - Two-step API flow: Transcribe (STT) → Ask (RAG + TTS)
 *   - Conversation history with audio playback
 *   - Full dashboard integration (recorded in Redis stats)
 */

const API_BASE = "http://localhost:8000";

// ── Configuration ──
const SILENCE_THRESHOLD = 0.015;    // Volume level considered "silence"
const SILENCE_DURATION_MS = 1800;   // How long silence before auto-stop (ms)
const WAVEFORM_BAR_COUNT = 24;      // Number of visualizer bars
const MIN_RECORDING_MS = 800;       // Minimum recording duration

// ── State ──
let state = "idle"; // idle | recording | transcribing | thinking | speaking
let mediaRecorder = null;
let audioChunks = [];
let audioContext = null;
let analyserNode = null;
let mediaStream = null;
let silenceTimer = null;
let recordingStartTime = 0;
let waveformAnimFrame = null;
let currentAudio = null;
let messageCount = 0;

// Session ID
const sessionId = localStorage.getItem("bkai_voice_session") || `voice_${Date.now()}`;
localStorage.setItem("bkai_voice_session", sessionId);

// ── DOM Elements ──
const micBtn = document.getElementById("micBtn");
const micRing = document.getElementById("micRing");
const micIcon = document.getElementById("micIcon");
const statusLabel = document.getElementById("statusLabel");
const statusHint = document.getElementById("statusHint");
const waveformEl = document.getElementById("waveform");
const conversationArea = document.getElementById("conversationArea");
const emptyState = document.getElementById("emptyState");
const sessionBadge = document.getElementById("sessionBadge");

// ── Initialize ──
function init() {
  generateWaveformBars();
  micBtn.addEventListener("click", handleMicClick);
  sessionBadge.textContent = `Phiên: ${sessionId.slice(-6)}`;
}

// ── Generate Waveform Bars ──
function generateWaveformBars() {
  waveformEl.innerHTML = "";
  for (let i = 0; i < WAVEFORM_BAR_COUNT; i++) {
    const bar = document.createElement("div");
    bar.className = "waveform-bar";
    bar.style.animationDelay = `${i * 0.05}s`;
    waveformEl.appendChild(bar);
  }
}

// ── Mic Button Click Handler ──
async function handleMicClick() {
  if (state === "idle") {
    await startRecording();
  } else if (state === "recording") {
    stopRecording();
  } else if (state === "speaking") {
    // Stop current audio playback
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    setState("idle");
  }
  // Ignore clicks during transcribing/thinking
}

// ── Start Recording ──
async function startRecording() {
  try {
    // Request microphone access
    if (!mediaStream) {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
          sampleRate: 16000,
        },
      });
    }

    // Setup Audio Context for VAD + Visualizer
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }

    const source = audioContext.createMediaStreamSource(mediaStream);
    analyserNode = audioContext.createAnalyser();
    analyserNode.fftSize = 256;
    analyserNode.smoothingTimeConstant = 0.7;
    source.connect(analyserNode);

    // Setup MediaRecorder
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";

    mediaRecorder = new MediaRecorder(mediaStream, { mimeType });
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
      const blob = new Blob(audioChunks, { type: mimeType });
      audioChunks = [];
      processRecording(blob);
    };

    // Start recording
    mediaRecorder.start(250); // Collect data every 250ms
    recordingStartTime = Date.now();

    setState("recording");

    // Start VAD + Waveform
    startVAD();
    startWaveformVisualization();

  } catch (err) {
    console.error("[Voice] Microphone error:", err);
    statusLabel.textContent = "Không có quyền truy cập micro";
    statusHint.textContent = "Vui lòng cấp quyền micro trong trình duyệt";
    micBtn.disabled = true;
    micBtn.style.opacity = "0.5";
  }
}

// ── Stop Recording ──
function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
  }
  stopVAD();
  stopWaveformVisualization();
}

// ── Voice Activity Detection (VAD) ──
function startVAD() {
  const bufferLength = analyserNode.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);
  let silenceStart = null;

  function checkSilence() {
    if (state !== "recording") return;

    analyserNode.getByteFrequencyData(dataArray);

    // Calculate average volume (0-1)
    let sum = 0;
    for (let i = 0; i < bufferLength; i++) {
      sum += dataArray[i];
    }
    const avgVolume = sum / bufferLength / 255;

    if (avgVolume < SILENCE_THRESHOLD) {
      // Silence detected
      if (!silenceStart) {
        silenceStart = Date.now();
      } else if (Date.now() - silenceStart >= SILENCE_DURATION_MS) {
        // Enough silence — auto stop (but only if we've recorded enough)
        const recordingDuration = Date.now() - recordingStartTime;
        if (recordingDuration >= MIN_RECORDING_MS) {
          stopRecording();
          return;
        }
      }
    } else {
      // Sound detected — reset silence timer
      silenceStart = null;
    }

    silenceTimer = requestAnimationFrame(checkSilence);
  }

  checkSilence();
}

function stopVAD() {
  if (silenceTimer) {
    cancelAnimationFrame(silenceTimer);
    silenceTimer = null;
  }
}

// ── Waveform Visualizer ──
function startWaveformVisualization() {
  const bars = waveformEl.querySelectorAll(".waveform-bar");
  const bufferLength = analyserNode.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);

  function draw() {
    if (state !== "recording") return;

    analyserNode.getByteFrequencyData(dataArray);

    // Map frequency data to bar heights
    const step = Math.floor(bufferLength / WAVEFORM_BAR_COUNT);
    for (let i = 0; i < WAVEFORM_BAR_COUNT; i++) {
      const value = dataArray[i * step] || 0;
      const height = Math.max(4, (value / 255) * 40);
      bars[i].style.height = `${height}px`;
      bars[i].style.opacity = `${0.3 + (value / 255) * 0.7}`;
    }

    waveformAnimFrame = requestAnimationFrame(draw);
  }

  draw();
}

function stopWaveformVisualization() {
  if (waveformAnimFrame) {
    cancelAnimationFrame(waveformAnimFrame);
    waveformAnimFrame = null;
  }
  // Reset bars
  const bars = waveformEl.querySelectorAll(".waveform-bar");
  bars.forEach((bar) => {
    bar.style.height = "8px";
    bar.style.opacity = "0.4";
  });
}

// ── Process Recording (2-step API flow) ──
async function processRecording(audioBlob) {
  // Check minimum size
  if (audioBlob.size < 1000) {
    setState("idle");
    statusLabel.textContent = "Ghi âm quá ngắn, vui lòng thử lại";
    setTimeout(() => {
      if (state === "idle") {
        statusLabel.textContent = "Nhấn để bắt đầu nói";
      }
    }, 2000);
    return;
  }

  // ── Step 1: Transcribe (STT) ──
  setState("transcribing");

  let userText;
  try {
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");

    const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    userText = data.text;

    if (!userText || !userText.trim()) {
      setState("idle");
      statusLabel.textContent = "Không nhận diện được giọng nói";
      setTimeout(() => {
        if (state === "idle") statusLabel.textContent = "Nhấn để bắt đầu nói";
      }, 2500);
      return;
    }
  } catch (err) {
    console.error("[Voice] STT error:", err);
    setState("idle");
    statusLabel.textContent = "Lỗi nhận diện giọng nói";
    statusHint.textContent = err.message || "Vui lòng thử lại";
    setTimeout(() => {
      if (state === "idle") {
        statusLabel.textContent = "Nhấn để bắt đầu nói";
        statusHint.textContent = "Tự động dừng khi phát hiện khoảng lặng";
      }
    }, 3000);
    return;
  }

  // Show user question immediately
  hideEmptyState();
  addUserMessage(userText);

  // ── Step 2: Ask RAG + TTS ──
  setState("thinking");

  try {
    const res = await fetch(`${API_BASE}/api/voice/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: userText,
        session_id: sessionId,
      }),
    });

    if (!res.ok) {
      throw new Error(`Server error: ${res.status}`);
    }

    // Check if response is JSON (TTS failed) or audio
    const contentType = res.headers.get("Content-Type") || "";

    if (contentType.includes("application/json")) {
      // TTS failed, text-only response
      const data = await res.json();
      addAIMessage(data.answer, null, {
        cached: data.cached,
        confidence: data.confidence,
      });
      setState("idle");
    } else {
      // Audio response — read headers for metadata
      const answerTextRaw = res.headers.get("X-Answer-Text");
      const confidence = parseFloat(res.headers.get("X-Confidence") || "0");
      const cached = res.headers.get("X-Cached") === "true";
      const responseTime = parseFloat(res.headers.get("X-Response-Time") || "0");

      let answerText = "";
      if (answerTextRaw) {
        try {
          answerText = decodeURIComponent(answerTextRaw);
        } catch {
          answerText = answerTextRaw;
        }
      }

      // Create audio blob URL
      const audioResponseBlob = await res.blob();
      const audioUrl = URL.createObjectURL(audioResponseBlob);

      addAIMessage(answerText, audioUrl, {
        cached,
        confidence,
        responseTime,
      });

      // Auto-play audio
      await playAudio(audioUrl);
    }
  } catch (err) {
    console.error("[Voice] Ask error:", err);
    addAIMessage("Xin lỗi, đã xảy ra lỗi khi xử lý. Vui lòng thử lại.", null, {});
    setState("idle");
  }
}

// ── Audio Playback ──
async function playAudio(audioUrl) {
  setState("speaking");

  try {
    currentAudio = new Audio(audioUrl);

    currentAudio.onended = () => {
      currentAudio = null;
      setState("idle");
    };

    currentAudio.onerror = () => {
      console.error("[Voice] Audio playback error");
      currentAudio = null;
      setState("idle");
    };

    await currentAudio.play();
  } catch (err) {
    console.error("[Voice] Play error:", err);
    setState("idle");
  }
}

// ── State Management ──
function setState(newState) {
  state = newState;

  // Reset all classes
  micBtn.classList.remove("recording", "processing", "speaking");
  micRing.classList.remove("active");
  waveformEl.classList.remove("active");
  micBtn.disabled = false;

  switch (newState) {
    case "idle":
      statusLabel.textContent = "Nhấn để bắt đầu nói";
      statusHint.textContent = "Tự động dừng khi phát hiện khoảng lặng";
      updateMicIcon("mic");
      break;

    case "recording":
      micBtn.classList.add("recording");
      micRing.classList.add("active");
      waveformEl.classList.add("active");
      statusLabel.textContent = "Đang nghe...";
      statusHint.textContent = "Nhấn lại để dừng ghi âm";
      updateMicIcon("stop");
      break;

    case "transcribing":
      micBtn.classList.add("processing");
      micBtn.disabled = true;
      statusLabel.textContent = "Đang nhận diện giọng nói...";
      statusHint.textContent = "faster-whisper đang xử lý";
      updateMicIcon("loading");
      break;

    case "thinking":
      micBtn.classList.add("processing");
      micBtn.disabled = true;
      statusLabel.textContent = "Đang suy nghĩ...";
      statusHint.textContent = "RAG Pipeline đang xử lý";
      updateMicIcon("loading");
      break;

    case "speaking":
      micBtn.classList.add("speaking");
      statusLabel.textContent = "Đang nói...";
      statusHint.textContent = "Nhấn để dừng phát";
      updateMicIcon("speaker");
      break;
  }
}

function updateMicIcon(type) {
  const paths = {
    mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"></rect>',
    loading: '<circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="32"><animate attributeName="stroke-dashoffset" dur="1s" values="32;0" repeatCount="indefinite"/></circle>',
    speaker: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>',
  };

  micIcon.innerHTML = paths[type] || paths.mic;
}

// ── Message Rendering ──
function hideEmptyState() {
  if (emptyState) {
    emptyState.style.display = "none";
  }
  // Shrink mic area to top when conversation starts
  const micArea = document.querySelector(".mic-area");
  if (micArea && !micArea.classList.contains("compact")) {
    micArea.classList.add("compact");
  }
}

function addUserMessage(text) {
  messageCount++;
  const msgHtml = `
    <div class="voice-message voice-msg-user" id="voiceMsg${messageCount}">
      <div class="voice-msg-bubble">${escapeHtml(text)}</div>
    </div>
  `;
  conversationArea.insertAdjacentHTML("beforeend", msgHtml);
  scrollToBottom();
}

function addAIMessage(text, audioUrl, metadata = {}) {
  messageCount++;
  const msgId = `voiceMsg${messageCount}`;

  let metaHtml = "";
  if (metadata.responseTime) {
    metaHtml += `<span class="voice-meta-chip">⏱ ${metadata.responseTime.toFixed(1)}s</span>`;
  }
  if (metadata.cached) {
    metaHtml += `<span class="voice-meta-chip" style="color: var(--success);">⚡ Cache</span>`;
  }
  if (metadata.confidence) {
    metaHtml += `<span class="voice-meta-chip">🎯 ${(metadata.confidence * 100).toFixed(0)}%</span>`;
  }

  let audioHtml = "";
  if (audioUrl) {
    audioHtml = `
      <div class="voice-audio-player">
        <button class="audio-play-btn" onclick="window.replayAudio('${audioUrl}', this)" title="Phát lại">
          ▶
        </button>
        <span class="audio-label">Phát lại câu trả lời</span>
      </div>
    `;
  }

  const formattedText = formatMarkdown(text);

  const msgHtml = `
    <div class="voice-message voice-msg-ai" id="${msgId}">
      <div class="voice-msg-avatar">BK</div>
      <div class="voice-msg-body">
        <div class="voice-msg-bubble">${formattedText}</div>
        ${audioHtml}
        <div class="voice-msg-meta">${metaHtml}</div>
      </div>
    </div>
  `;
  conversationArea.insertAdjacentHTML("beforeend", msgHtml);
  scrollToBottom();
}

// ── Replay Audio ──
window.replayAudio = async function (audioUrl, btn) {
  // Stop any currently playing audio
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
    currentAudio = null;
    setState("idle");
  }

  try {
    currentAudio = new Audio(audioUrl);
    btn.textContent = "⏸";

    currentAudio.onended = () => {
      btn.textContent = "▶";
      currentAudio = null;
    };

    currentAudio.onerror = () => {
      btn.textContent = "▶";
      currentAudio = null;
    };

    await currentAudio.play();
  } catch (err) {
    console.error("[Voice] Replay error:", err);
    btn.textContent = "▶";
  }
};

// ── Utilities ──
function scrollToBottom() {
  requestAnimationFrame(() => {
    conversationArea.scrollTop = conversationArea.scrollHeight;
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function formatMarkdown(text) {
  if (!text) return "";
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    .replace(/\n/g, "<br>")
    .replace(
      /^- (.+)/gm,
      '<span style="display:flex;gap:8px;margin:2px 0"><span style="color:var(--accent-light)">•</span><span>$1</span></span>'
    );
}

// ── Start ──
init();
