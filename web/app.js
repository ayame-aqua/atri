const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const statusEl = document.getElementById("status");
const nameEl = document.getElementById("character-name");

const ERROR_TEXT = {
  BAD_REQUEST: "消息不完整",
  DUPLICATE: "这条已经处理过了",
  LLM_FAILED: "她这会儿没接上",
  INTERNAL: "内部出错了",
};

let socket = null;
let busy = false;

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

function sendText() {
  const text = (inputEl.value || "").trim();
  if (!text || busy || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  const messageId = newMessageId();
  busy = true;
  sendBtn.disabled = true;
  appendMessage("user", text);
  inputEl.value = "";
  socket.send(JSON.stringify({ type: "user_text", message_id: messageId, text }));
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${proto}://${location.host}/ws/chat`);
  socket.addEventListener("open", () => setStatus("在线"));
  socket.addEventListener("close", () => {
    setStatus("掉线了，刷新页面");
    busy = false;
    sendBtn.disabled = false;
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
      } else if (frame.state === "idle") {
        setStatus("在线");
        busy = false;
        sendBtn.disabled = false;
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
    if (frame.type === "error") {
      const mapped = ERROR_TEXT[frame.code] || frame.message || "出错了";
      setStatus(mapped);
      appendMessage("assistant", mapped);
      busy = false;
      sendBtn.disabled = false;
    }
  });
}

sendBtn.addEventListener("click", sendText);
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
