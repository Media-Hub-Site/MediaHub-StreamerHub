"""
ui/main_window.py
─────────────────
Ventana principal de StreamStudio: sidebar animada + barra superior con perfil real de Twitch +
páginas con transición e integración real con Twitch OAuth 2.0, Helix API, IRC bidireccional y OBS Studio.
"""

import os
import random
import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread
from PyQt6.QtGui import QIcon, QGuiApplication
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame

from core.storage import StorageManager
from core.tts_engine import TTSEngine
from core.overlay_server import OverlayServer
from core.twitch_client import TwitchIRCBridge, TwitchHelixClient

from . import theme as T
from .widgets import Sidebar, AnimatedStack, Avatar, make_button, show_toast
from .pages import (
    DashboardPage, ActivityPage, OverlaysPage, VoicesPage, RewardsPage, ConnectionPage,
)

APP_VERSION = "v1.2.0"

SAMPLE_VIEWERS = [
    "xX_KamiStreamer_Xx", "NekoValkyrie", "DarkRaiderCL", "PixelSamurai99",
    "AstroNova_TV", "TacoSaurio", "CyberValhalla", "LunaGaming_cl",
]


class TwitchSyncWorker(QThread):
    """Valida el token OAuth y sincroniza perfil, stream, seguidores y clave con Twitch Helix API."""
    finished_sync = pyqtSignal(dict)

    def __init__(self, oauth_token: str, client_id: str = "", channel_hint: str = "", parent=None):
        super().__init__(parent)
        self.oauth_token = oauth_token
        self.client_id = client_id
        self.channel_hint = channel_hint

    def run(self):
        snap = TwitchHelixClient.fetch_account_snapshot(
            self.oauth_token, self.client_id, self.channel_hint
        )
        self.finished_sync.emit(snap)


class TwitchUpdateStreamWorker(QThread):
    """Actualiza en segundo plano el título del stream y la categoría/juego en Twitch Helix API."""
    finished_update = pyqtSignal(bool, str, str, str)

    def __init__(self, oauth_token: str, client_id: str, user_id: str, title: str, game: str, parent=None):
        super().__init__(parent)
        self.oauth_token = oauth_token
        self.client_id = client_id
        self.user_id = user_id
        self.title = title
        self.game = game

    def run(self):
        ok, msg, resolved_game = TwitchHelixClient.update_stream_info(
            self.oauth_token, self.client_id, self.user_id, self.title, self.game
        )
        self.finished_update.emit(ok, msg, self.title, resolved_game)


class StreamStudioWindow(QMainWindow):
    data_changed = pyqtSignal()
    connection_changed = pyqtSignal(bool, str)
    chat_received = pyqtSignal(str, str)
    profile_updated = pyqtSignal(dict)
    _oauth_callback_signal = pyqtSignal(str)

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
        self._sync_worker: TwitchSyncWorker | None = None
        self._update_worker: TwitchUpdateStreamWorker | None = None
        self._known_follower_names: set[str] = set()

        # Recibir token desde el callback HTTP local (/api/auth/token) de forma thread-safe
        self._oauth_callback_signal.connect(self._on_browser_oauth_token)
        self.overlay_server.on_oauth_token = lambda tok: self._oauth_callback_signal.emit(tok)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._do_autosave)

        # Poller periódico (cada 30 s) para sincronizar estado LIVE y nuevos seguidores reales
        self._helix_timer = QTimer(self)
        self._helix_timer.setInterval(30000)
        self._helix_timer.timeout.connect(self._poll_helix_quietly)

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
        disp = tw.get("display_name") or tw.get("channel")
        if disp:
            self.top_avatar.set_name(disp)
            self.top_channel.setText(disp)
        if tw.get("auto_connect"):
            if tw.get("oauth_token"):
                QTimer.singleShot(300, lambda: self.authenticate_and_sync(
                    tw.get("oauth_token", ""),
                    tw.get("client_id", ""),
                    tw.get("channel", ""),
                    silent=True,
                ))
            elif tw.get("channel"):
                QTimer.singleShot(300, lambda: self.connect_twitch(tw["channel"], ""))

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
        self.sidebar.add_item(6, "⚙", "Cuenta y transmisión", g3)
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
        self.top_status.setMinimumWidth(84)
        l.addWidget(self.top_status)
        self._style_status(False)

        self.top_avatar = Avatar(40)
        l.addWidget(self.top_avatar)
        col = QVBoxLayout()
        col.setSpacing(0)
        cap = QLabel("CHANNEL")
        cap.setStyleSheet(f"color:{T.MUTED}; font-size:7.5pt; font-weight:800; letter-spacing:1px;")
        self.top_channel = QLabel("Sin canal configurado")
        self.top_channel.setStyleSheet("font-weight:700;")
        col.addWidget(cap)
        col.addWidget(self.top_channel)
        l.addLayout(col)

        self.btn_top_auth = make_button("Login Twitch", "Purple")
        self.btn_top_auth.clicked.connect(self.go_to_connection)
        l.addWidget(self.btn_top_auth)

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

    def _style_status(self, live: bool, viewers: int = 0):
        color = T.RED if live else T.MUTED
        text = f"LIVE • {viewers}" if (live and viewers > 0) else ("EN VIVO" if live else "OFFLINE")
        self.top_status.setText(text)
        self.top_status.setStyleSheet(
            f"background:{'rgba(248,113,113,0.16)' if live else '#2A2E42'}; color:{color}; "
            "font-size:8pt; font-weight:800; padding:6px 10px; border-radius:6px;")

    def _on_nav(self, idx: int):
        if idx == 2:
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

    # ── Autenticación Real Twitch OAuth 2.0 + Helix API + IRC ─────────────────
    def start_browser_oauth(self, client_id: str = ""):
        cid = (client_id or "").strip()
        if cid:
            auth_url = TwitchHelixClient.build_oauth_url(cid, self.port)
            webbrowser.open(auth_url)
            self.toast("Autoriza en tu navegador; StreamStudio recibirá el token automáticamente", T.ACCENT)
        else:
            webbrowser.open(f"http://127.0.0.1:{self.port}/auth/callback")
            self.toast("Pasarela OAuth local abierta en el navegador", T.ACCENT)

    def _on_browser_oauth_token(self, token: str):
        self.activateWindow()
        self.raise_()
        self.authenticate_and_sync(token)

    def authenticate_and_sync(self, oauth_token: str, client_id: str = "", channel_hint: str = "", silent: bool = False):
        if not oauth_token.strip():
            if not silent:
                self.toast("Ingresa un Token OAuth de Twitch válido", T.YELLOW)
            return

        if self._sync_worker and self._sync_worker.isRunning():
            return

        if not silent:
            self.toast("Validando cuenta con Twitch Helix API…", T.ACCENT)

        self._sync_worker = TwitchSyncWorker(oauth_token, client_id, channel_hint, self)
        self._sync_worker.finished_sync.connect(lambda snap: self._on_sync_finished(snap, silent))
        self._sync_worker.start()

    def _on_sync_finished(self, snap: dict, silent: bool = False):
        if not snap.get("ok"):
            if not silent:
                self.toast(snap.get("error", "No se pudo validar el token de Twitch"), T.RED)
            return

        tw = self.storage.data.setdefault("twitch", {})
        tw["oauth_token"] = snap.get("token", tw.get("oauth_token", ""))
        tw["client_id"] = snap.get("client_id", tw.get("client_id", ""))
        tw["user_id"] = snap.get("user_id", tw.get("user_id", ""))
        tw["channel"] = snap.get("login", tw.get("channel", ""))
        tw["display_name"] = snap.get("display_name", tw["channel"])
        tw["profile_image_url"] = snap.get("profile_image_url", "")
        tw["broadcaster_type"] = snap.get("broadcaster_type", "")
        tw["stream_title"] = snap.get("stream_title", tw.get("stream_title", ""))
        tw["stream_game"] = snap.get("stream_game", tw.get("stream_game", ""))
        tw["is_live"] = bool(snap.get("is_live", False))
        tw["viewer_count"] = int(snap.get("viewer_count", 0))
        tw["scopes"] = snap.get("scopes", [])

        if snap.get("followers_total") is not None:
            tw["followers_total"] = int(snap["followers_total"])
            self.storage.data["overlay"]["follower_goal_current"] = int(snap["followers_total"])

        if snap.get("stream_key"):
            tw["stream_key"] = snap["stream_key"]

        # Detectar nuevos seguidores reales
        recent_flw = snap.get("recent_followers", [])
        if recent_flw:
            if not self._known_follower_names:
                self._known_follower_names = {f["user_name"] for f in recent_flw if f.get("user_name")}
            else:
                for f in recent_flw:
                    uname = f.get("user_name", "")
                    if uname and uname not in self._known_follower_names:
                        self._known_follower_names.add(uname)
                        self.process_event(
                            "follow", uname, "¡Nuevo seguidor real en tu canal de Twitch!", 0, "NUEVO SEGUIDOR • TWITCH"
                        )

        self.storage.save()

        # Actualizar Topbar con avatar real y nombre visible
        disp = tw["display_name"] or tw["channel"]
        self.top_avatar.set_name(disp)
        if snap.get("avatar_bytes"):
            self.top_avatar.set_image_bytes(snap["avatar_bytes"])
        self.top_channel.setText(disp)
        self.btn_top_auth.setText("Cuenta Conectada")
        self._style_status(tw["is_live"] or self.twitch_connected, tw["viewer_count"])

        self.profile_updated.emit(snap)
        self.data_changed.emit()

        # Conectar chat IRC autenticado automáticamente si no está conectado aún
        if tw["channel"] and not self.twitch_connected:
            self.connect_twitch(tw["channel"], tw["oauth_token"], bot_login=tw["channel"])

        if not self._helix_timer.isActive():
            self._helix_timer.start()

        if not silent:
            self.toast(f"¡Conectado a Twitch como {disp}!", T.GREEN)

    def _poll_helix_quietly(self):
        tw = self.storage.data.get("twitch", {})
        if tw.get("oauth_token"):
            self.authenticate_and_sync(
                tw["oauth_token"], tw.get("client_id", ""), tw.get("channel", ""), silent=True
            )

    def update_twitch_stream_metadata(self, title: str, game: str):
        tw = self.storage.data.get("twitch", {})
        tok = tw.get("oauth_token", "")
        if not tok:
            self.toast("Primero vincula tu Token OAuth en 'Cuenta y transmisión'", T.YELLOW)
            self.go_to_connection()
            return

        if self._update_worker and self._update_worker.isRunning():
            return

        self.toast("Actualizando información del stream en Twitch…", T.ACCENT)
        self._update_worker = TwitchUpdateStreamWorker(
            tok, tw.get("client_id", ""), tw.get("user_id", ""), title, game, self
        )
        self._update_worker.finished_update.connect(self._on_stream_metadata_updated)
        self._update_worker.start()

    def _on_stream_metadata_updated(self, ok: bool, msg: str, title: str, resolved_game: str):
        if ok:
            tw = self.storage.data.setdefault("twitch", {})
            tw["stream_title"] = title
            tw["stream_game"] = resolved_game
            self.storage.save()
            self.profile_updated.emit({"stream_title": title, "stream_game": resolved_game})
        self.toast(msg, T.GREEN if ok else T.RED)

    def send_chat_message(self, text: str) -> bool:
        if not self.twitch_connected:
            self.toast("Conéctate primero al canal de Twitch", T.YELLOW)
            return False
        if not self.twitch_bridge.authenticated:
            self.toast("Para enviar mensajes al chat necesitas iniciar sesión con Token OAuth", T.YELLOW)
            return False
        ok = self.twitch_bridge.send_message(text)
        if ok and text.strip().lower().startswith(("!tts ", "!voz ")):
            spoken = text.strip().split(" ", 1)[1].strip()
            if spoken:
                self.process_event("channel_points", self.twitch_bridge.nick, spoken, 100, "COMANDO CHAT • VOZ IA", use_tts=True)
        return ok

    def logout_twitch(self):
        self._helix_timer.stop()
        self.disconnect_twitch()
        tw = self.storage.data.setdefault("twitch", {})
        tw["oauth_token"] = ""
        tw["user_id"] = ""
        tw["display_name"] = ""
        tw["profile_image_url"] = ""
        tw["is_live"] = False
        tw["viewer_count"] = 0
        self.storage.save()
        self.top_avatar.set_image_bytes(None)
        self.top_avatar.set_name("S")
        self.top_channel.setText("Sin canal configurado")
        self.btn_top_auth.setText("Login Twitch")
        self._style_status(False)
        self.profile_updated.emit({"login": "", "token": "", "display_name": "Cuenta no vinculada"})
        self.toast("Sesión de Twitch cerrada", T.YELLOW)

    def connect_twitch(self, channel: str, token: str = "", bot_login: str = ""):
        if not channel:
            self.toast("Ingresa el nombre de tu canal de Twitch", T.YELLOW)
            return
        tw = self.storage.data.setdefault("twitch", {})
        tw["channel"] = channel
        if token:
            tw["oauth_token"] = token
        self.storage.save()
        disp = tw.get("display_name") or channel
        self.top_avatar.set_name(disp)
        self.top_channel.setText(disp)
        self.twitch_status = f"Conectando a #{channel}…"
        self.connection_changed.emit(False, self.twitch_status)
        self.twitch_bridge.connect_channel(channel, token or tw.get("oauth_token", ""), bot_login=bot_login or channel)

    def disconnect_twitch(self):
        self.twitch_bridge.disconnect_channel()

    def _on_status(self, connected: bool, text: str):
        self.twitch_connected = connected
        self.twitch_status = text
        tw = self.storage.data.get("twitch", {})
        self._style_status(connected or tw.get("is_live", False), tw.get("viewer_count", 0))
        self.connection_changed.emit(connected, text)

    def _on_chat(self, user: str, text: str):
        self.overlay_server.push_chat(user, text)
        self.chat_received.emit(user, text)

    def _on_twitch_event(self, etype: str, user: str, message: str, amount: int, badge: str):
        self.process_event(etype, user, message, amount, badge,
                           use_tts=etype in ("sub", "bits", "channel_points", "raid"))

    def closeEvent(self, event):
        self._helix_timer.stop()
        self.tts.stop_current()
        self.twitch_bridge.disconnect_channel()
        self.overlay_server.stop()
        self.storage.save()
        super().closeEvent(event)
