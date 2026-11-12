"""
ui/main_window.py
─────────────────
Ventana principal de StreamStudio: sidebar animada + barra superior + páginas con transición.
Actúa como controlador (ctx) para las páginas: eventos, TTS, overlay local y conexión a Twitch.
"""

import os
import random
import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QGuiApplication
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame

from core.storage import StorageManager
from core.tts_engine import TTSEngine
from core.overlay_server import OverlayServer
from core.twitch_client import TwitchIRCBridge

from . import theme as T
from .widgets import Sidebar, AnimatedStack, Avatar, make_button, show_toast
from .pages import (
    DashboardPage, ActivityPage, OverlaysPage, VoicesPage, RewardsPage, ConnectionPage,
)

APP_VERSION = "v1.1.0"

SAMPLE_VIEWERS = [
    "xX_KamiStreamer_Xx", "NekoValkyrie", "DarkRaiderCL", "PixelSamurai99",
    "AstroNova_TV", "TacoSaurio", "CyberValhalla", "LunaGaming_cl",
]


class StreamStudioWindow(QMainWindow):
    data_changed = pyqtSignal()
    connection_changed = pyqtSignal(bool, str)
    chat_received = pyqtSignal(str, str)

    def __init__(self, lang: str = "es"):
        super().__init__()
        self.lang = lang if lang in ("es", "en") else "es"
        self.storage = StorageManager()
        self.tts = TTSEngine(self.storage)
        self.overlay_server = OverlayServer(self.storage)
        self.port = self.overlay_server.start()
        self.active_port = self.port
        self.twitch_bridge = TwitchIRCBridge(self)
        self.twitch_connected = False
        self.twitch_status = "Sin conexión"

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._do_autosave)

        self.setWindowTitle("StreamStudio — Studio de alertas, voces IA y analíticas para Twitch")
        self.resize(1280, 820)
        self.setMinimumSize(1080, 700)
        self._base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon = os.path.join(self._base_dir, "assets", "hub", "Media-Hub.ico")
        if os.path.isfile(icon):
            self.setWindowIcon(QIcon(icon))

        self._build_ui()

        self.twitch_bridge.chat_received.connect(self._on_chat)
        self.twitch_bridge.event_received.connect(self._on_twitch_event)
        self.twitch_bridge.status_changed.connect(self._on_status)

        tw = self.storage.data.get("twitch", {})
        if tw.get("channel"):
            self.top_avatar.set_name(tw["channel"])
            self.top_channel.setText(tw["channel"])
        if tw.get("auto_connect") and tw.get("channel"):
            self.connect_twitch(tw["channel"], tw.get("oauth_token", ""))

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        logo = os.path.join(self._base_dir, "assets", "hub", "streamstudio.png")
        self.sidebar = Sidebar(logo, APP_VERSION)
        self.sidebar.add_item(0, "▦", "Dashboard")
        self.sidebar.add_item(1, "☰", "Feed de actividad")
        self.sidebar.add_item(2, "▶", "Vista previa OBS")
        g1 = self.sidebar.add_group("ALERTAS Y OVERLAYS")
        self.sidebar.add_item(3, "❖", "Overlays y metas", g1)
        g2 = self.sidebar.add_group("VOCES IA Y LEALTAD")
        self.sidebar.add_item(4, "♪", "Voces IA", g2)
        self.sidebar.add_item(5, "★", "Recompensas", g2)
        g3 = self.sidebar.add_group("CUENTA")
        self.sidebar.add_item(6, "⚙", "Conexión y analíticas", g3)
        self.sidebar.finish()
        h.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self._build_topbar())

        self.stack = AnimatedStack()
        self.pages = [
            DashboardPage(self), ActivityPage(self), QWidget(),
            OverlaysPage(self), VoicesPage(self), RewardsPage(self), ConnectionPage(self),
        ]
        for p in self.pages:
            self.stack.addWidget(p)
        right.addWidget(self.stack, 1)
        h.addLayout(right, 1)

        self._page_index = 0
        self.sidebar.selected.connect(self._on_nav)
        self.sidebar.select(0, animated=False, emit=False)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(64)
        l = QHBoxLayout(bar)
        l.setContentsMargins(24, 0, 24, 0)
        l.setSpacing(14)

        self.top_status = QLabel("OFFLINE")
        self.top_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.top_status.setFixedHeight(26)
        self.top_status.setMinimumWidth(78)
        l.addWidget(self.top_status)
        self._style_status(False)

        self.top_avatar = Avatar(40)
        l.addWidget(self.top_avatar)
        col = QVBoxLayout()
        col.setSpacing(0)
        cap = QLabel("CANAL")
        cap.setStyleSheet(f"color:{T.MUTED}; font-size:7.5pt; font-weight:800; letter-spacing:1px;")
        self.top_channel = QLabel("Sin canal configurado")
        self.top_channel.setStyleSheet("font-weight:700;")
        col.addWidget(cap)
        col.addWidget(self.top_channel)
        l.addLayout(col)
        l.addStretch()

        url = f"http://127.0.0.1:{self.port}/overlay"
        srv = QLabel(f"● OBS  127.0.0.1:{self.port}")
        srv.setToolTip(url)
        srv.setStyleSheet(f"color:{T.GREEN}; font-size:9pt; font-weight:700; font-family:Consolas;")
        l.addWidget(srv)
        b1 = make_button("Copiar URL OBS", "Ghost")
        b1.clicked.connect(lambda: self.copy_url(url))
        b2 = make_button("Vista previa", "Primary")
        b2.clicked.connect(lambda: self.open_preview(url))
        b3 = make_button("Detener voz IA", "Danger")
        b3.clicked.connect(self.tts.stop_current)
        for b in (b1, b2, b3):
            l.addWidget(b)
        return bar

    def _style_status(self, live: bool):
        color = T.RED if live else T.MUTED
        text = "EN VIVO" if live else "OFFLINE"
        self.top_status.setText(text)
        self.top_status.setStyleSheet(
            f"background:{'rgba(248,113,113,0.16)' if live else '#2A2E42'}; color:{color}; "
            "font-size:8pt; font-weight:800; padding:6px 10px; border-radius:6px;")

    def _on_nav(self, idx: int):
        if idx == 2:  # Vista previa OBS abre el navegador y no cambia de página
            self.open_preview(f"http://127.0.0.1:{self.port}/overlay")
            self.sidebar.select(self._page_index, emit=False)
            return
        self._page_index = idx
        self.stack.slide_to(idx)

    def go_to_connection(self):
        self.sidebar.select(6)

    # ── Utilidades para páginas ───────────────────────────────────────────────
    def toast(self, text: str, color: str = T.GREEN):
        show_toast(self, text, color)

    def copy_url(self, url: str):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(url)
        self.toast("URL copiada. Pégala en una fuente Navegador de OBS", T.ACCENT)

    def open_preview(self, url: str):
        sep = "&" if "?" in url else "?"
        webbrowser.open(url if "preview=1" in url else f"{url}{sep}preview=1")

    def autosave(self):
        self._save_timer.start()

    def _do_autosave(self):
        self.storage.save()
        self.toast("Cambios guardados y aplicados a OBS")

    # ── Eventos del stream ────────────────────────────────────────────────────
    def simulate(self, event_type: str):
        user = random.choice(SAMPLE_VIEWERS)
        if event_type == "follow":
            self.process_event("follow", user, "¡Nuevo seguidor en el canal de Twitch!", 0,
                               "NUEVO SEGUIDOR • TWITCH", use_tts=False)
        elif event_type == "sub":
            self.process_event("sub", user, f"¡{user} se ha suscrito al canal! ¡Gracias por el apoyo!", 1,
                               "NUEVO SUSCRIPTOR • TIER 1", use_tts=True)
        elif event_type == "bits":
            self.process_event("bits", user, f"¡{user} envió 500 Bits! ¡El directo está increíble!", 500,
                               "CHEER • 500 BITS", use_tts=True)
        elif event_type == "raid":
            self.process_event("raid", user, f"¡{user} ha llegado con una Raid de 45 espectadores!", 45,
                               "RAID EN VIVO • 45 VIEWERS", use_tts=True)
        else:
            rewards = [r for r in self.storage.data.get("rewards", []) if r.get("enabled", True)]
            rw = random.choice(rewards) if rewards else {
                "title": "Mensaje con Voz IA", "cost": 500, "persona": "narrador_epico",
                "alert_badge": "PUNTOS • VOZ IA"}
            self.process_event("channel_points", user,
                               f"{user} canjeó '{rw['title']}': ¡saludo épico para todo el chat!",
                               int(rw.get("cost", 500)), rw.get("alert_badge", "PUNTOS DEL CANAL • VOZ IA"),
                               use_tts=True, persona=rw.get("persona"))

    def process_event(self, event_type, username, message, amount=0, badge="ALERTA EN VIVO",
                      use_tts=False, persona=None, force_tts=False):
        spoken = self.tts.speak(message, persona_id=persona, force=force_tts) if use_tts else ""
        evt = self.storage.record_event(event_type=event_type, username=username,
                                        message=spoken or message, amount=amount,
                                        tts_used=bool(spoken), badge=badge)
        self.overlay_server.push_alert(evt)
        self.data_changed.emit()

    def replay(self, evt: dict):
        if evt.get("tts_used"):
            self.tts.speak(evt.get("message", ""), force=True)
        copy = dict(evt)
        copy["id"] = f"replay_{random.randint(10000, 99999)}"
        self.overlay_server.push_alert(copy)
        self.toast("Alerta reenviada a OBS", T.ACCENT)

    # ── Twitch ────────────────────────────────────────────────────────────────
    def connect_twitch(self, channel: str, token: str = ""):
        if not channel:
            self.toast("Ingresa el nombre de tu canal de Twitch", T.YELLOW)
            return
        tw = self.storage.data.setdefault("twitch", {})
        tw["channel"], tw["oauth_token"] = channel, token
        self.storage.save()
        self.top_avatar.set_name(channel)
        self.top_channel.setText(channel)
        self.twitch_status = f"Conectando a #{channel}…"
        self.connection_changed.emit(False, self.twitch_status)
        self.twitch_bridge.connect_channel(channel, token)

    def disconnect_twitch(self):
        self.twitch_bridge.disconnect_channel()

    def _on_status(self, connected: bool, text: str):
        self.twitch_connected = connected
        self.twitch_status = text
        self._style_status(connected)
        self.connection_changed.emit(connected, text)

    def _on_chat(self, user: str, text: str):
        self.overlay_server.push_chat(user, text)
        self.chat_received.emit(user, text)

    def _on_twitch_event(self, etype: str, user: str, message: str, amount: int, badge: str):
        self.process_event(etype, user, message, amount, badge,
                           use_tts=etype in ("sub", "bits", "channel_points", "raid"))

    def closeEvent(self, event):
        self.tts.stop_current()
        self.twitch_bridge.disconnect_channel()
        self.overlay_server.stop()
        self.storage.save()
        super().closeEvent(event)
