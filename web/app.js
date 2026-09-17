// P1：接 /ws/chat；此处仅占位，避免空文件
const statusEl = document.getElementById("status");
const sendBtn = document.getElementById("send");

sendBtn?.addEventListener("click", () => {
  if (statusEl) {
    statusEl.textContent = "后端尚未接线：先完成 P1 WebSocket。";
  }
});
