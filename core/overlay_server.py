"""
core/overlay_server.py
──────────────────────
Servidor HTTP local para OBS Studio Browser Sources (http://127.0.0.1:8899).
Sirve overlays HTML5 transparentes en tiempo real para Alertas, Voces IA,
Chat en vivo y Barras de Metas (Seguidores / Suscriptores) sin requerir servicios externos.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


OVERLAY_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>StreamStudio OBS Overlay</title>
<style>
  :root {
    --accent: #9146FF;
    --accent-glow: rgba(145, 70, 255, 0.55);
    --bg-card: rgba(15, 23, 42, 0.92);
    --text-main: #FFFFFF;
    --text-sub: #CBD5E1;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: transparent;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    overflow: hidden;
    width: 100vw;
    height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: center;
    padding: 32px;
    color: var(--text-main);
  }
  body.preview-mode {
    background: radial-gradient(circle at center, #1E1B4B 0%, #090D16 100%);
  }
  .preview-banner {
    display: none;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(145, 70, 255, 0.5);
    padding: 8px 18px;
    border-radius: 999px;
    font-size: 13px;
    color: #E2E8F0;
    backdrop-filter: blur(8px);
  }
  body.preview-mode .preview-banner {
    display: inline-block;
  }

  /* Tarjeta de Alerta Principal */
  .alert-stage {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
  }
  .alert-box {
    min-width: 480px;
    max-width: 680px;
    background: var(--bg-card);
    border: 2px solid var(--accent);
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.65), 0 0 35px var(--accent-glow);
    border-radius: 20px;
    padding: 26px 32px;
    text-align: center;
    transform: translateY(-40px) scale(0.88);
    opacity: 0;
    transition: all 0.45s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    pointer-events: none;
    position: relative;
    overflow: hidden;
  }
  .alert-box.visible {
    transform: translateY(0) scale(1);
    opacity: 1;
  }
  .alert-badge {
    display: inline-block;
    background: var(--accent);
    color: #FFFFFF;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 5px 14px;
    border-radius: 999px;
    margin-bottom: 12px;
  }
  .alert-user {
    font-size: 32px;
    font-weight: 900;
    color: #FFFFFF;
    text-shadow: 0 2px 12px var(--accent-glow);
    margin-bottom: 8px;
  }
  .alert-message {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-sub);
    line-height: 1.4;
    word-wrap: break-word;
  }
  .tts-wave {
    display: none;
    margin-top: 14px;
    justify-content: center;
    align-items: center;
    gap: 5px;
    height: 22px;
  }
  .tts-wave.active {
    display: flex;
  }
  .bar {
    width: 5px;
    height: 8px;
    background: var(--accent);
    border-radius: 4px;
    animation: soundWave 0.6s infinite ease-in-out alternate;
  }
  .bar:nth-child(2) { animation-delay: 0.1s; }
  .bar:nth-child(3) { animation-delay: 0.2s; }
  .bar:nth-child(4) { animation-delay: 0.3s; }
  .bar:nth-child(5) { animation-delay: 0.15s; }
  @keyframes soundWave {
    0% { height: 6px; opacity: 0.5; }
    100% { height: 22px; opacity: 1; }
  }

  /* Barra de Metas Inferior */
  .goals-bar {
    display: flex;
    gap: 24px;
    width: 100%;
    max-width: 780px;
    justify-content: center;
  }
  .goal-pill {
    flex: 1;
    background: rgba(15, 23, 42, 0.88);
    border: 1px solid rgba(148, 163, 184, 0.28);
    border-radius: 14px;
    padding: 12px 18px;
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.45);
  }
  .goal-header {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 6px;
    color: #F8FAFC;
  }
  .goal-track {
    width: 100%;
    height: 10px;
    background: rgba(30, 41, 59, 0.95);
    border-radius: 99px;
    overflow: hidden;
  }
  .goal-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), #38BDF8);
    border-radius: 99px;
    transition: width 0.5s ease;
  }
</style>
</head>
<body>
  <div class="preview-banner">
    Vista Previa StreamStudio • En OBS Studio el fondo es 100% transparente
  </div>

  <div class="alert-stage">
    <div id="alertBox" class="alert-box">
      <div id="alertBadge" class="alert-badge">NUEVA ALERTA</div>
      <div id="alertUser" class="alert-user">StreamerUser</div>
      <div id="alertMsg" class="alert-message">¡Gracias por apoyar el canal!</div>
      <div id="ttsWave" class="tts-wave">
        <div class="bar"></div><div class="bar"></div><div class="bar"></div><div class="bar"></div><div class="bar"></div>
        <span style="font-size:12px; font-weight:700; margin-left:8px; color:#E2E8F0;">VOZ IA ACTIVA</span>
      </div>
    </div>
  </div>

  <div id="goalsContainer" class="goals-bar">
    <div class="goal-pill">
      <div class="goal-header">
        <span>META DE SEGUIDORES</span>
        <span id="followGoalTxt">0 / 100</span>
      </div>
      <div class="goal-track"><div id="followGoalFill" class="goal-fill" style="width: 40%;"></div></div>
    </div>
    <div class="goal-pill">
      <div class="goal-header">
        <span>META DE SUSCRIPTORES</span>
        <span id="subGoalTxt">0 / 25</span>
      </div>
      <div class="goal-track"><div id="subGoalFill" class="goal-fill" style="width: 30%;"></div></div>
    </div>
  </div>

<script>
  const params = new URLSearchParams(window.location.search);
  if (params.get("preview") === "1") {
    document.body.classList.add("preview-mode");
  }
  if (params.get("mode") === "goals") {
    document.querySelector(".alert-stage").style.display = "none";
  }

  const THEMES = {
    twitch_purple: { accent: "#9146FF", glow: "rgba(145, 70, 255, 0.55)" },
    cyber_cyan:    { accent: "#06B6D4", glow: "rgba(6, 182, 212, 0.55)" },
    emerald_neon:  { accent: "#10B981", glow: "rgba(16, 185, 129, 0.55)" },
    crimson_fire:  { accent: "#EF4444", glow: "rgba(239, 68, 68, 0.55)" }
  };

  let lastAlertId = null;
  let hideTimeout = null;

  function playChime(type) {
    if (type === "mute") return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const notes = type === "fanfare" ? [523.25, 659.25, 783.99, 1046.5]
                  : type === "arcade"  ? [440, 554.37, 659.25, 880]
                  : type === "cyber"   ? [330, 660, 493.88, 987.77]
                  : [587.33, 880, 1174.66];
      notes.forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = type === "cyber" ? "sawtooth" : "triangle";
        osc.frequency.setValueAtTime(freq, ctx.currentTime + idx * 0.11);
        gain.gain.setValueAtTime(0.16, ctx.currentTime + idx * 0.11);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + idx * 0.11 + 0.35);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + idx * 0.11);
        osc.stop(ctx.currentTime + idx * 0.11 + 0.36);
      });
    } catch (e) {}
  }

  async function pollState() {
    try {
      const res = await fetch("/api/state");
      const data = await res.json();
      const ov = data.overlay || {};
      const theme = THEMES[ov.theme] || THEMES.twitch_purple;
      document.documentElement.style.setProperty("--accent", theme.accent);
      document.documentElement.style.setProperty("--accent-glow", theme.glow);

      const goalsContainer = document.getElementById("goalsContainer");
      if (ov.show_goals_in_overlay === false && params.get("mode") !== "goals") {
        goalsContainer.style.display = "none";
      } else {
        goalsContainer.style.display = "flex";
        const fc = ov.follower_goal_current || 0;
        const ft = Math.max(1, ov.follower_goal_target || 100);
        const sc = ov.sub_goal_current || 0;
        const st = Math.max(1, ov.sub_goal_target || 25);
        document.getElementById("followGoalTxt").textContent = `${fc} / ${ft}`;
        document.getElementById("followGoalFill").style.width = `${Math.min(100, (fc / ft) * 100)}%`;
        document.getElementById("subGoalTxt").textContent = `${sc} / ${st}`;
        document.getElementById("subGoalFill").style.width = `${Math.min(100, (sc / st) * 100)}%`;
      }

      const alert = data.active_alert;
      if (alert && alert.id && alert.id !== lastAlertId) {
        lastAlertId = alert.id;
        document.getElementById("alertBadge").textContent = alert.badge || "ALERTA EN VIVO";
        document.getElementById("alertUser").textContent = alert.username || "Streamer";
        document.getElementById("alertMsg").textContent = alert.message || "";
        const wave = document.getElementById("ttsWave");
        if (alert.tts_used) {
          wave.classList.add("active");
        } else {
          wave.classList.remove("active");
        }
        const box = document.getElementById("alertBox");
        box.classList.add("visible");
        playChime(ov.sound_chime || "crystal");

        if (hideTimeout) clearTimeout(hideTimeout);
        const dur = (ov.duration_sec || 6) * 1000;
        hideTimeout = setTimeout(() => {
          box.classList.remove("visible");
        }, dur);
      }
    } catch (e) {}
  }

  setInterval(pollState, 600);
  pollState();
</script>
</body>
</html>
"""

CHAT_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>StreamStudio Chat Overlay</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: transparent;
    font-family: 'Segoe UI', system-ui, sans-serif;
    padding: 20px;
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    height: 100vh;
    overflow: hidden;
  }
  .chat-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-width: 480px;
  }
  .chat-msg {
    background: rgba(15, 23, 42, 0.85);
    border-left: 4px solid #9146FF;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 15px;
    line-height: 1.35;
    box-shadow: 0 4px 14px rgba(0,0,0,0.45);
    animation: slideIn 0.25s ease-out;
  }
  .chat-user {
    font-weight: 800;
    color: #C084FC;
    margin-right: 6px;
  }
  @keyframes slideIn {
    from { transform: translateX(-20px); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
</style>
</head>
<body>
  <div id="chatList" class="chat-list"></div>
<script>
  async function pollChat() {
    try {
      const res = await fetch("/api/state");
      const data = await res.json();
      const msgs = data.recent_chat || [];
      const container = document.getElementById("chatList");
      container.innerHTML = msgs.slice(0, 12).reverse().map(m =>
        `<div class="chat-msg"><span class="chat-user">${m.user}:</span><span>${m.text}</span></div>`
      ).join("");
    } catch (e) {}
  }
  setInterval(pollChat, 800);
  pollChat();
</script>
</body>
</html>
"""


class OverlayServer:
    def __init__(self, storage):
        self.storage = storage
        self.active_alert: dict | None = None
        self.recent_chat: list[dict] = []
        self.port = int(self.storage.data.get("overlay", {}).get("port", 8899))
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.is_running = False

    def start(self) -> int:
        if self.is_running:
            return self.port

        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Silenciar logs de consola

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                if path in ("/", "/overlay", "/goals"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(OVERLAY_HTML.encode("utf-8"))
                elif path == "/chat":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(CHAT_HTML.encode("utf-8"))
                elif path == "/api/state":
                    payload = {
                        "overlay": parent.storage.data.get("overlay", {}),
                        "active_alert": parent.active_alert,
                        "recent_chat": parent.recent_chat[:15],
                    }
                    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(raw)
                else:
                    self.send_response(404)
                    self.end_headers()

        # Intentar puerto configurado o buscar uno libre cercano
        for candidate_port in range(self.port, self.port + 15):
            try:
                self._httpd = ThreadingHTTPServer(("127.0.0.1", candidate_port), Handler)
                self.port = candidate_port
                self.is_running = True
                self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
                self._thread.start()
                break
            except OSError:
                continue

        return self.port

    def push_alert(self, evt: dict):
        self.active_alert = evt

    def push_chat(self, user: str, text: str):
        self.recent_chat.insert(0, {"user": user, "text": text})
        if len(self.recent_chat) > 30:
            self.recent_chat = self.recent_chat[:30]

    def stop(self):
        if self._httpd:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
        self.is_running = False
