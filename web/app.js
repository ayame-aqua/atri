const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const liveBtn = document.getElementById("live");
const statusEl = document.getElementById("status");
const vadMeterEl = document.getElementById("vad-meter");
const nameEl = document.getElementById("character-name");

const ERROR_TEXT = {
  BAD_REQUEST: "消息不完整",
  DUPLICATE: "这条已经处理过了",
  LLM_FAILED: "她这会儿没接上",
  INTERNAL: "内部出错了",
};

const RECORD_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
];

const VAD_MIN_SPEECH_MS = 400;
const VAD_SILENCE_MS = 800;
const VAD_MAX_UTTER_MS = 7000;
const VAD_POLL_MS = 40;
const VAD_TIMESLICE_MS = 200;
const VAD_SPEECH_HZ_LO = 250;
const VAD_SPEECH_HZ_HI = 3800;
const VAD_SPEAK_OVER_FLOOR = 0.06;
const VAD_SPEAK_RATIO = 2.2;
const VAD_SILENCE_RATIO = 1.4;
const VAD_FLOOR_EMA = 0.1;
const VAD_FLOOR_MIN = 0.01;
const VAD_REPORT_MS = 200;
const ANALYSER_FFT_SIZE = 2048;

let socket = null;
let busy = false;
let currentAudio = null;
let liveMode = false;
let liveStream = null;
let audioContext = null;
let analyser = null;
let sourceNode = null;
let vadTimer = null;
let mediaRecorder = null;
let recordChunks = [];
let sendAfterStop = false;
let speechStartedAt = 0;
let silenceStartedAt = 0;
let utteranceStartedAt = 0;
let noiseFloor = VAD_FLOOR_MIN;
let peakBand = 0;
let lastVadReportAt = 0;

function isSpeaking() {
  return Boolean(currentAudio && !currentAudio.paused && !currentAudio.ended);
}

function isRecording() {
  return mediaRecorder !== null;
}

function listeningStatus() {
  return liveMode ? "在听…" : "在线";
}

function syncComposer() {
  const socketOpen = Boolean(socket && socket.readyState === WebSocket.OPEN);
  sendBtn.disabled = busy || !socketOpen || isRecording();
  if (liveBtn) {
    liveBtn.disabled = !socketOpen;
    liveBtn.textContent = liveMode ? "结束" : "对话";
    liveBtn.classList.toggle("live-on", liveMode);
  }
}

function playAssistantAudio(url) {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio = null;
  }
  const audio = new Audio(url);
  currentAudio = audio;
  const clearIfCurrent = () => {
    if (currentAudio === audio) {
      currentAudio = null;
    }
    if (!busy) {
      setStatus(listeningStatus());
    }
    syncComposer();
  };
  audio.addEventListener("ended", clearIfCurrent);
  audio.addEventListener("pause", () => {
    if (audio.ended) {
      return;
    }
    syncComposer();
  });
  audio.play()
    .then(() => {
      setStatus("她在说话");
      syncComposer();
    })
    .catch(() => {
      setStatus("语音播放失败");
      clearIfCurrent();
    });
}

function setStatus(text) {
  if (statusEl) {
    statusEl.textContent = text;
  }
}

function appendMessage(role, text) {
  const row = document.createElement("div");
  row.className = `msg ${role}`;
  const who = document.createElement("div");
  who.className = "who";
  who.textContent = role === "user" ? "你" : nameEl?.textContent || "她";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  row.append(who, bubble);
  messagesEl.append(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function newMessageId() {
  return crypto.randomUUID();
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

function pickRecordMime() {
  if (typeof MediaRecorder === "undefined") {
    return "";
  }
  for (const mime of RECORD_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(mime)) {
      return mime;
    }
  }
  return "";
}

function currentBand() {
  if (!analyser || !audioContext) {
    return 0;
  }
  const freq = new Uint8Array(analyser.frequencyBinCount);
  analyser.getByteFrequencyData(freq);
  const binHz = audioContext.sampleRate / analyser.fftSize;
  const low = Math.max(1, Math.floor(VAD_SPEECH_HZ_LO / binHz));
  const high = Math.min(freq.length - 1, Math.ceil(VAD_SPEECH_HZ_HI / binHz));
  let sum = 0;
  let count = 0;
  for (let index = low; index <= high; index += 1) {
    sum += freq[index];
    count += 1;
  }
  return count ? sum / count / 255 : 0;
}

function isVoiceOn(band) {
  const overFloor = Math.max(noiseFloor * VAD_SPEAK_RATIO, noiseFloor + VAD_SPEAK_OVER_FLOOR);
  return band >= overFloor;
}

function isVoiceOff(band) {
  return band <= noiseFloor * VAD_SILENCE_RATIO;
}

function percent(value) {
  return `${Math.round(Math.max(0, value) * 100)}%`;
}

function publishVad(band) {
  const voice = isVoiceOn(band);
  const snapshot = {
    band,
    floor: noiseFloor,
    peak: peakBand,
    recording: isRecording(),
    voice,
    busy,
    speaking: isSpeaking(),
  };
  window.__natsumeVad = snapshot;
  if (vadMeterEl) {
    vadMeterEl.hidden = false;
    const bar = "▮".repeat(Math.min(20, Math.round(band * 20)))
      + "▯".repeat(Math.max(0, 20 - Math.round(band * 20)));
    const state = snapshot.recording ? "采集中" : (voice ? "过线" : "安静");
    vadMeterEl.textContent = `音量 ${percent(band)} ${bar} 底噪 ${percent(noiseFloor)} 峰值 ${percent(peakBand)} ${state}`;
  }
  const now = Date.now();
  if (now - lastVadReportAt < VAD_REPORT_MS) {
    return;
  }
  lastVadReportAt = now;
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  socket.send(JSON.stringify({
    type: "vad_level",
    band,
    floor: noiseFloor,
    peak: peakBand,
    recording: snapshot.recording,
    voice,
  }));
}

function updateNoiseFloor(band) {
  if (band >= noiseFloor * VAD_SILENCE_RATIO) {
    return;
  }
  noiseFloor = noiseFloor * (1 - VAD_FLOOR_EMA) + band * VAD_FLOOR_EMA;
  if (noiseFloor < VAD_FLOOR_MIN) {
    noiseFloor = VAD_FLOOR_MIN;
  }
}

function stopTracks() {
  if (!liveStream) {
    return;
  }
  for (const track of liveStream.getTracks()) {
    track.stop();
  }
  liveStream = null;
}

function closeAudioGraph() {
  if (vadTimer !== null) {
    window.clearInterval(vadTimer);
    vadTimer = null;
  }
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }
  analyser = null;
  if (audioContext) {
    void audioContext.close();
    audioContext = null;
  }
}

function resetVadClock() {
  speechStartedAt = 0;
  silenceStartedAt = 0;
  utteranceStartedAt = 0;
  peakBand = 0;
}

function cancelUtterance() {
  sendAfterStop = false;
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
    return;
  }
  recordChunks = [];
  resetVadClock();
}

function stopUtterance() {
  if (!mediaRecorder || mediaRecorder.state === "inactive") {
    return;
  }
  sendAfterStop = true;
  mediaRecorder.stop();
}

function beginUtterance() {
  if (!liveStream || isRecording() || busy || isSpeaking()) {
    return;
  }
  const mime = pickRecordMime();
  recordChunks = [];
  sendAfterStop = true;
  mediaRecorder = mime
    ? new MediaRecorder(liveStream, { mimeType: mime })
    : new MediaRecorder(liveStream);
  const usedMime = mediaRecorder.mimeType || mime || "audio/webm";
  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      recordChunks.push(event.data);
    }
  });
  mediaRecorder.addEventListener("stop", () => {
    mediaRecorder = null;
    const shouldSend = sendAfterStop;
    sendAfterStop = false;
    resetVadClock();
    if (shouldSend) {
      void sendRecording(usedMime);
    } else {
      recordChunks = [];
      syncComposer();
    }
  }, { once: true });
  utteranceStartedAt = Date.now();
  silenceStartedAt = 0;
  peakBand = 0;
  mediaRecorder.start(VAD_TIMESLICE_MS);
  setStatus("在听你说…");
  syncComposer();
}

function vadTick() {
  if (!liveMode || !analyser) {
    return;
  }
  if (audioContext && audioContext.state === "suspended") {
    void audioContext.resume();
  }
  const band = currentBand();
  publishVad(band);
  if (busy || isSpeaking()) {
    if (isRecording()) {
      cancelUtterance();
    }
    resetVadClock();
    return;
  }
  const now = Date.now();
  if (!isRecording()) {
    updateNoiseFloor(band);
    if (isVoiceOn(band)) {
      if (!speechStartedAt) {
        speechStartedAt = now;
      }
      if (now - speechStartedAt >= VAD_MIN_SPEECH_MS) {
        beginUtterance();
        peakBand = band;
      }
    } else {
      speechStartedAt = 0;
    }
    return;
  }
  if (band > peakBand) {
    peakBand = band;
  }
  if (now - utteranceStartedAt >= VAD_MAX_UTTER_MS) {
    stopUtterance();
    return;
  }
  if (isVoiceOff(band)) {
    if (!silenceStartedAt) {
      silenceStartedAt = now;
    }
    if (now - silenceStartedAt >= VAD_SILENCE_MS) {
      stopUtterance();
    }
  } else {
    silenceStartedAt = 0;
  }
}

async function startLive() {
  if (liveMode || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("这个浏览器不能录音");
    return;
  }
  try {
    liveStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
  } catch {
    setStatus("没有麦克风权限");
    return;
  }
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context) {
    stopTracks();
    setStatus("这个浏览器不能实时听");
    return;
  }
  audioContext = new Context();
  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }
  sourceNode = audioContext.createMediaStreamSource(liveStream);
  analyser = audioContext.createAnalyser();
  analyser.fftSize = ANALYSER_FFT_SIZE;
  analyser.smoothingTimeConstant = 0.35;
  sourceNode.connect(analyser);
  liveMode = true;
  noiseFloor = VAD_FLOOR_MIN;
  resetVadClock();
  vadTimer = window.setInterval(vadTick, VAD_POLL_MS);
  setStatus("在听…");
  syncComposer();
}

function stopLive() {
  liveMode = false;
  if (isRecording()) {
    cancelUtterance();
  }
  closeAudioGraph();
  stopTracks();
  resetVadClock();
  if (vadMeterEl) {
    vadMeterEl.hidden = true;
  }
  if (!busy && !isSpeaking()) {
    setStatus("在线");
  }
  syncComposer();
}

function toggleLive() {
  if (liveMode) {
    stopLive();
    return;
  }
  void startLive();
}

async function sendRecording(mime) {
  const blob = new Blob(recordChunks, { type: mime });
  recordChunks = [];
  if (!blob.size || !socket || socket.readyState !== WebSocket.OPEN) {
    if (liveMode) {
      setStatus("在听…");
    } else {
      setStatus("没听清");
    }
    busy = false;
    syncComposer();
    return;
  }
  busy = true;
  syncComposer();
  setStatus("正在听…");
  try {
    const data = await blobToBase64(blob);
    socket.send(JSON.stringify({
      type: "user_audio",
      message_id: newMessageId(),
      mime,
      data_base64: data,
    }));
  } catch {
    setStatus(liveMode ? "在听…" : "录音发送失败");
    busy = false;
    syncComposer();
  }
}

function sendText() {
  const text = (inputEl.value || "").trim();
  if (!text || busy || isRecording() || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  const messageId = newMessageId();
  busy = true;
  syncComposer();
  appendMessage("user", text);
  inputEl.value = "";
  socket.send(JSON.stringify({ type: "user_text", message_id: messageId, text }));
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws/chat`);
  socket.addEventListener("open", () => {
    setStatus(listeningStatus());
    syncComposer();
  });
  socket.addEventListener("close", () => {
    if (liveMode) {
      stopLive();
    }
    setStatus("掉线了，刷新页面");
    busy = false;
    syncComposer();
  });
  socket.addEventListener("message", (event) => {
    let frame;
    try {
      frame = JSON.parse(event.data);
    } catch {
      setStatus("收到无法解析的消息");
      return;
    }
    if (frame.type === "status") {
      if (frame.state === "thinking") {
        setStatus("她在想…");
      } else if (frame.state === "tts_failed") {
        setStatus("语音合成失败，文字还在");
      } else if (frame.state === "unclear") {
        setStatus(liveMode ? "在听…" : (frame.message || "没听清"));
      } else if (frame.state === "idle") {
        busy = false;
        if (!isSpeaking()) {
          setStatus(listeningStatus());
        }
        syncComposer();
      }
      return;
    }
    if (frame.type === "user_transcript") {
      if (frame.unclear) {
        return;
      }
      const text = typeof frame.text === "string" ? frame.text.trim() : "";
      if (text) {
        appendMessage("user", text);
      }
      return;
    }
    if (frame.type === "assistant_text") {
      const text = Array.isArray(frame.texts) ? frame.texts.join("\n") : "";
      if (text) {
        appendMessage("assistant", text);
      }
      return;
    }
    if (frame.type === "assistant_audio") {
      if (typeof frame.url === "string" && frame.url) {
        playAssistantAudio(frame.url);
      }
      return;
    }
    if (frame.type === "error") {
      const mapped = ERROR_TEXT[frame.code] || frame.message || "出错了";
      setStatus(mapped);
      appendMessage("assistant", mapped);
      busy = false;
      syncComposer();
    }
  });
}

sendBtn.addEventListener("click", sendText);
if (liveBtn) {
  liveBtn.addEventListener("click", toggleLive);
}
inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendText();
  }
});

fetch("/api/character")
  .then((res) => res.json())
  .then((data) => {
    if (data.name) {
      nameEl.textContent = data.name;
      document.title = data.name;
    }
  })
  .catch(() => {});

connect();
syncComposer();
