const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const recordBtn = document.getElementById("record");
const statusEl = document.getElementById("status");
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

let socket = null;
let busy = false;
let currentAudio = null;
let mediaRecorder = null;
let recordChunks = [];
let recordStream = null;

function isSpeaking() {
  return Boolean(currentAudio && !currentAudio.paused && !currentAudio.ended);
}

function isRecording() {
  return mediaRecorder !== null;
}

function syncComposer() {
  const socketOpen = Boolean(socket && socket.readyState === WebSocket.OPEN);
  sendBtn.disabled = busy || !socketOpen || isRecording();
  if (recordBtn) {
    recordBtn.disabled = !socketOpen || busy || isSpeaking();
    recordBtn.textContent = isRecording() ? "停止" : "录音";
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
      setStatus("在线");
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

function stopTracks() {
  if (!recordStream) {
    return;
  }
  for (const track of recordStream.getTracks()) {
    track.stop();
  }
  recordStream = null;
}

async function startRecording() {
  if (busy || isSpeaking() || isRecording() || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("这个浏览器不能录音");
    return;
  }
  const mime = pickRecordMime();
  try {
    recordStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    setStatus("没有麦克风权限");
    return;
  }
  recordChunks = [];
  mediaRecorder = mime
    ? new MediaRecorder(recordStream, { mimeType: mime })
    : new MediaRecorder(recordStream);
  mediaRecorder.addEventListener("dataavailable", (event) => {
    if (event.data && event.data.size > 0) {
      recordChunks.push(event.data);
    }
  });
  mediaRecorder.addEventListener("stop", () => {
    const usedMime = mediaRecorder ? mediaRecorder.mimeType : mime;
    mediaRecorder = null;
    stopTracks();
    void sendRecording(usedMime || "audio/webm");
  });
  mediaRecorder.start();
  setStatus("录音中…");
  syncComposer();
}

function stopRecording() {
  if (!mediaRecorder) {
    return;
  }
  mediaRecorder.stop();
}

async function sendRecording(mime) {
  const blob = new Blob(recordChunks, { type: mime });
  recordChunks = [];
  if (!blob.size || !socket || socket.readyState !== WebSocket.OPEN) {
    setStatus("没听清");
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
    setStatus("录音发送失败");
    busy = false;
    syncComposer();
  }
}

function toggleRecord() {
  if (isRecording()) {
    stopRecording();
    return;
  }
  void startRecording();
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
    setStatus("在线");
    syncComposer();
  });
  socket.addEventListener("close", () => {
    setStatus("掉线了，刷新页面");
    busy = false;
    if (isRecording()) {
      mediaRecorder.stop();
    }
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
        setStatus(frame.message || "没听清");
      } else if (frame.state === "idle") {
        if (!isSpeaking()) {
          setStatus("在线");
        }
        busy = false;
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
if (recordBtn) {
  recordBtn.addEventListener("click", toggleRecord);
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
