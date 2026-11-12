"""
ui/main_window.py
─────────────────
Ventana Principal de StreamStudio — Suite Local-First para Streamers de Twitch.
Integra:
1. Panel de Control y Simulador de Alertas en Tiempo Real (Follow, Sub, Bits, Raid, Puntos IA)
2. Estudio de Overlays OBS (Browser Sources listos para copiar y previsualizar, Temas y Metas)
3. Motor de Voces IA y Recompensas de Puntos del Canal + Moderación SafeStream Guard
4. Conector Twitch en Vivo (IRC / EventSub) y Analíticas con Exportación CSV
"""

import os
import csv
import random
import webbrowser
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QFrame, QGridLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLineEdit, QComboBox, QMessageBox, QSpinBox, QCheckBox,
    QFileDialog, QAbstractItemView, QSlider
)
from PyQt6.QtGui import QIcon, QColor, QBrush, QGuiApplication
from PyQt6.QtCore import Qt

from core.storage import StorageManager
from core.tts_engine import TTSEngine, VOICE_PERSONAS
from core.overlay_server import OverlayServer
from core.twitch_client import TwitchIRCBridge


SAMPLE_VIEWERS = [
    "xX_KamiStreamer_Xx", "NekoValkyrie", "DarkRaiderCL", "PixelSamurai99",
    "AstroNova_TV", "TacoSaurio", "CyberValhalla", "LunaGaming_cl"
]


class StreamStudioWindow(QMainWindow):
    def __init__(self, lang: str = "es"):
        super().__init__()
        self.lang = lang if lang in ("es", "en") else "es"
        self.storage = StorageManager()
        self.tts = TTSEngine(self.storage)
        self.overlay_server = OverlayServer(self.storage)
        self.active_port = self.overlay_server.start()
        self.twitch_bridge = TwitchIRCBridge(self)

        self.setWindowTitle(
            "StreamStudio — Alertas OBS, Voces IA, Puntos de Canal y Analíticas para Twitch"
            if self.lang == "es"
            else "StreamStudio — OBS Alerts, AI Voices, Channel Points & Analytics for Twitch"
        )
        self.resize(1180, 780)
        self.setMinimumSize(1020, 680)

        self._setup_icon()
        self.init_ui()
        self._apply_theme()

        # Conectar señales de Twitch IRC en vivo
        self.twitch_bridge.chat_received.connect(self._on_twitch_chat)
        self.twitch_bridge.event_received.connect(self._on_twitch_event)
        self.twitch_bridge.status_changed.connect(self._on_twitch_status)

        # Poblar tablas e indicadores iniciales
        self._refresh_all_views()

        # Auto-conectar si estaba configurado
        tw_cfg = self.storage.data.get("twitch", {})
        if tw_cfg.get("auto_connect") and tw_cfg.get("channel"):
            self.twitch_bridge.connect_channel(
                tw_cfg.get("channel", ""),
                tw_cfg.get("oauth_token", ""),
            )

    def _setup_icon(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "assets", "hub", "Media-Hub.ico")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(24, 18, 24, 18)
        root_layout.setSpacing(14)

        # ── 1. Header Bento ───────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_lbl = QLabel("StreamStudio")
        title_lbl.setStyleSheet("font-size: 21pt; font-weight: 800; color: #FFFFFF;")
        subtitle_lbl = QLabel(
            "Alertas Interactivas para OBS • Puntos del Canal con Voces IA • Analíticas en Tiempo Real para Twitch"
        )
        subtitle_lbl.setStyleSheet("font-size: 9.5pt; color: #A78BFA;")

        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        # Badge estado del servidor OBS
        self.lbl_server_badge = QLabel(f"● OBS Server: http://127.0.0.1:{self.active_port}/overlay")
        self.lbl_server_badge.setStyleSheet("""
            background-color: rgba(145, 70, 255, 0.16);
            color: #C4B5FD;
            border: 1px solid #8B5CF6;
            border-radius: 8px;
            padding: 6px 12px;
            font-weight: 700;
            font-size: 9.5pt;
        """)
        header_layout.addWidget(self.lbl_server_badge)

        # Botón Copiar URL OBS
        btn_copy_obs = QPushButton("Copiar URL OBS")
        btn_copy_obs.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy_obs.setFixedHeight(36)
        btn_copy_obs.setStyleSheet(self._btn_style("#7C3AED", "#6D28D9"))
        btn_copy_obs.clicked.connect(lambda: self._copy_url(f"http://127.0.0.1:{self.active_port}/overlay"))
        header_layout.addWidget(btn_copy_obs)

        # Botón Vista Previa Overlay
        btn_preview = QPushButton("Abrir Vista Previa")
        btn_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_preview.setFixedHeight(36)
        btn_preview.setStyleSheet(self._btn_style("#2563EB", "#1D4ED8"))
        btn_preview.clicked.connect(lambda: webbrowser.open(f"http://127.0.0.1:{self.active_port}/overlay?preview=1"))
        header_layout.addWidget(btn_preview)

        # Botón Silenciar Voz IA en curso
        btn_stop_tts = QPushButton("Detener Voz IA")
        btn_stop_tts.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_stop_tts.setFixedHeight(36)
        btn_stop_tts.setStyleSheet(self._btn_style("#DC2626", "#B91C1C"))
        btn_stop_tts.clicked.connect(self.tts.stop_current)
        header_layout.addWidget(btn_stop_tts)

        root_layout.addLayout(header_layout)

        # ── 2. Pestañas Principales ───────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #1E293B;
                background-color: #0F172A;
                border-radius: 12px;
                padding: 12px;
            }
            QTabBar::tab {
                background-color: #1E293B;
                color: #94A3B8;
                padding: 10px 20px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 700;
                font-size: 9.5pt;
            }
            QTabBar::tab:selected {
                background-color: #7C3AED;
                color: #FFFFFF;
            }
        """)

        self.tab_dashboard = QWidget()
        self.tab_overlays = QWidget()
        self.tab_ai_voices = QWidget()
        self.tab_twitch = QWidget()

        self._init_dashboard_tab()
        self._init_overlays_tab()
        self._init_ai_voices_tab()
        self._init_twitch_tab()

        self.tabs.addTab(self.tab_dashboard, "Panel En Vivo & Simulador")
        self.tabs.addTab(self.tab_overlays, "Overlays OBS & Metas")
        self.tabs.addTab(self.tab_ai_voices, "Voces IA & Puntos del Canal")
        self.tabs.addTab(self.tab_twitch, "Conexión Twitch & Analíticas")

        root_layout.addWidget(self.tabs, 1)

    # ─────────────────────────────────────────────────────────────────────────
    #  Tab 1: Panel de Control & Simulador de Alertas en Tiempo Real
    # ─────────────────────────────────────────────────────────────────────────

    def _init_dashboard_tab(self):
        layout = QVBoxLayout(self.tab_dashboard)
        layout.setSpacing(12)

        # 4 Tarjetas de Métricas
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)

        self.card_follows = self._create_metric_card("Seguidores (Sesión)", "0", "Nuevos Follows en Twitch", "#A78BFA")
        self.card_subs = self._create_metric_card("Suscriptores", "0", "Subs Tier 1/2/3 & Regalos", "#38BDF8")
        self.card_bits = self._create_metric_card("Bits & Cheers", "0", "Total de Bits recibidos", "#FBBF24")
        self.card_points = self._create_metric_card("Canjes Puntos IA", "0", "Recompensas con Voz IA activadas", "#34D399")

        metrics_grid.addWidget(self.card_follows[0], 0, 0)
        metrics_grid.addWidget(self.card_subs[0], 0, 1)
        metrics_grid.addWidget(self.card_bits[0], 0, 2)
        metrics_grid.addWidget(self.card_points[0], 0, 3)
        layout.addLayout(metrics_grid)

        # Barra de Simulador Rápido de Eventos Twitch
        sim_frame = QFrame()
        sim_frame.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        sim_layout = QHBoxLayout(sim_frame)
        sim_layout.setSpacing(10)

        sim_lbl = QLabel("Probar Alertas en OBS + Voz IA:")
        sim_lbl.setStyleSheet("font-weight: 800; color: #E2E8F0; font-size: 9.5pt; border: none;")
        sim_layout.addWidget(sim_lbl)

        btn_sim_follow = QPushButton("＋ Nuevo Follow")
        btn_sim_follow.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sim_follow.setStyleSheet(self._btn_style("#7C3AED", "#6D28D9"))
        btn_sim_follow.clicked.connect(lambda: self._trigger_simulated_event("follow"))
        sim_layout.addWidget(btn_sim_follow)

        btn_sim_sub = QPushButton("★ Nueva Suscripción (Voz IA)")
        btn_sim_sub.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sim_sub.setStyleSheet(self._btn_style("#2563EB", "#1D4ED8"))
        btn_sim_sub.clicked.connect(lambda: self._trigger_simulated_event("sub"))
        sim_layout.addWidget(btn_sim_sub)

        btn_sim_bits = QPushButton("💎 Donar 500 Bits (Voz IA)")
        btn_sim_bits.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sim_bits.setStyleSheet(self._btn_style("#D97706", "#B45309"))
        btn_sim_bits.clicked.connect(lambda: self._trigger_simulated_event("bits"))
        sim_layout.addWidget(btn_sim_bits)

        btn_sim_raid = QPushButton("🚀 Raid de 45 Viewers")
        btn_sim_raid.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sim_raid.setStyleSheet(self._btn_style("#E11D48", "#BE123C"))
        btn_sim_raid.clicked.connect(lambda: self._trigger_simulated_event("raid"))
        sim_layout.addWidget(btn_sim_raid)

        btn_sim_points = QPushButton("🎙️ Canje Puntos del Canal + Voz IA")
        btn_sim_points.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sim_points.setStyleSheet(self._btn_style("#059669", "#047857"))
        btn_sim_points.clicked.connect(lambda: self._trigger_simulated_event("channel_points"))
        sim_layout.addWidget(btn_sim_points)

        layout.addWidget(sim_frame)

        # Tabla de Feed de Actividad en Tiempo Real
        feed_title = QLabel("Feed de Eventos Recientes en el Stream (Haz clic en 'Repetir' para reenviar a OBS)")
        feed_title.setStyleSheet("font-weight: 700; color: #94A3B8; font-size: 9.5pt;")
        layout.addWidget(feed_title)

        self.tbl_events = QTableWidget(0, 6)
        self.tbl_events.setHorizontalHeaderLabels([
            "Hora", "Categoría", "Usuario Twitch", "Mensaje / Detalle de Alerta", "Voz IA", "Acción OBS"
        ])
        self._style_table(self.tbl_events, stretch_col=3)
        layout.addWidget(self.tbl_events, 1)

    # ─────────────────────────────────────────────────────────────────────────
    #  Tab 2: Estudio de Overlays OBS & Configurador de Metas
    # ─────────────────────────────────────────────────────────────────────────

    def _init_overlays_tab(self):
        layout = QVBoxLayout(self.tab_overlays)
        layout.setSpacing(14)

        # Sección 1: Fuentes de Navegador (Browser Sources) para OBS Studio
        urls_frame = QFrame()
        urls_frame.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        urls_layout = QVBoxLayout(urls_frame)
        urls_title = QLabel("1. Fuentes de Navegador (Browser Sources) listas para OBS Studio")
        urls_title.setStyleSheet("font-size: 11pt; font-weight: 800; color: #FFFFFF; border: none;")
        urls_sub = QLabel(
            "En OBS Studio añade una fuente 'Navegador' (Browser Source), pega cualquiera de estas URLs locales "
            "con ancho 1280 y alto 720. El fondo será automáticamente transparente."
        )
        urls_sub.setStyleSheet("font-size: 9.5pt; color: #94A3B8; border: none;")
        urls_layout.addWidget(urls_title)
        urls_layout.addWidget(urls_sub)

        sources = [
            ("Overlay Completo (Alertas + Voz IA + Metas):", f"http://127.0.0.1:{self.active_port}/overlay"),
            ("Widget de Chat Transparente en Vivo:", f"http://127.0.0.1:{self.active_port}/chat"),
            ("Barra Independiente de Metas (Goals):", f"http://127.0.0.1:{self.active_port}/goals?mode=goals"),
        ]
        for label_txt, url_val in sources:
            row = QHBoxLayout()
            lbl = QLabel(label_txt)
            lbl.setFixedWidth(310)
            lbl.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
            inp = QLineEdit(url_val)
            inp.setReadOnly(True)
            inp.setStyleSheet("""
                QLineEdit {
                    background-color: #0F172A;
                    color: #38BDF8;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    padding: 6px 10px;
                    font-family: Consolas, monospace;
                    font-weight: 700;
                }
            """)
            btn_cp = QPushButton("Copiar URL")
            btn_cp.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cp.setStyleSheet(self._btn_style("#7C3AED", "#6D28D9"))
            btn_cp.clicked.connect(lambda _, u=url_val: self._copy_url(u))

            btn_open = QPushButton("Probar en Navegador")
            btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_open.setStyleSheet(self._btn_style("#334155", "#475569"))
            preview_u = f"{url_val}&preview=1" if "?" in url_val else f"{url_val}?preview=1"
            btn_open.clicked.connect(lambda _, u=preview_u: webbrowser.open(u))

            row.addWidget(lbl)
            row.addWidget(inp, 1)
            row.addWidget(btn_cp)
            row.addWidget(btn_open)
            urls_layout.addLayout(row)

        layout.addWidget(urls_frame)

        # Sección 2: Personalización Visual y Metas del Canal
        cfg_frame = QFrame()
        cfg_frame.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        cfg_grid = QGridLayout(cfg_frame)
        cfg_grid.setSpacing(12)

        ov = self.storage.data.get("overlay", {})

        lbl_theme = QLabel("Tema Visual del Overlay:")
        lbl_theme.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.cmb_overlay_theme = QComboBox()
        self.cmb_overlay_theme.addItem("Twitch Purple (Morado Neón)", "twitch_purple")
        self.cmb_overlay_theme.addItem("Cyberpunk Cyan (Azul Eléctrico)", "cyber_cyan")
        self.cmb_overlay_theme.addItem("Emerald Matrix (Verde Esmeralda)", "emerald_neon")
        self.cmb_overlay_theme.addItem("Crimson Boss (Rojo Intenso)", "crimson_fire")
        idx_t = self.cmb_overlay_theme.findData(ov.get("theme", "twitch_purple"))
        if idx_t >= 0:
            self.cmb_overlay_theme.setCurrentIndex(idx_t)

        lbl_chime = QLabel("Sonido de Alerta en OBS:")
        lbl_chime.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.cmb_chime = QComboBox()
        self.cmb_chime.addItem("Cristal Armónico", "crystal")
        self.cmb_chime.addItem("Arcade Retro 8-Bit", "arcade")
        self.cmb_chime.addItem("Fanfarria Épica", "fanfare")
        self.cmb_chime.addItem("Sintetizador Cyber", "cyber")
        self.cmb_chime.addItem("Sin Sonido (Mudo)", "mute")
        idx_c = self.cmb_chime.findData(ov.get("sound_chime", "crystal"))
        if idx_c >= 0:
            self.cmb_chime.setCurrentIndex(idx_c)

        lbl_dur = QLabel("Duración en Pantalla (seg):")
        lbl_dur.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.spn_duration = QSpinBox()
        self.spn_duration.setRange(3, 25)
        self.spn_duration.setValue(int(ov.get("duration_sec", 6)))

        self.chk_show_goals = QCheckBox("Mostrar Barra de Metas en el Overlay Principal")
        self.chk_show_goals.setChecked(bool(ov.get("show_goals_in_overlay", True)))
        self.chk_show_goals.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")

        # Metas de Seguidores y Suscriptores
        lbl_fg = QLabel("Meta de Seguidores (Actual / Objetivo):")
        lbl_fg.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.spn_follow_cur = QSpinBox()
        self.spn_follow_cur.setRange(0, 1000000)
        self.spn_follow_cur.setValue(int(ov.get("follower_goal_current", 42)))
        self.spn_follow_tar = QSpinBox()
        self.spn_follow_tar.setRange(1, 1000000)
        self.spn_follow_tar.setValue(int(ov.get("follower_goal_target", 100)))

        lbl_sg = QLabel("Meta de Suscriptores (Actual / Objetivo):")
        lbl_sg.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.spn_sub_cur = QSpinBox()
        self.spn_sub_cur.setRange(0, 100000)
        self.spn_sub_cur.setValue(int(ov.get("sub_goal_current", 8)))
        self.spn_sub_tar = QSpinBox()
        self.spn_sub_tar.setRange(1, 100000)
        self.spn_sub_tar.setValue(int(ov.get("sub_goal_target", 25)))

        btn_save_ov = QPushButton("Guardar y Actualizar Overlays en Tiempo Real")
        btn_save_ov.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_ov.setFixedHeight(38)
        btn_save_ov.setStyleSheet(self._btn_style("#059669", "#047857"))
        btn_save_ov.clicked.connect(self._save_overlay_settings)

        cfg_grid.addWidget(lbl_theme, 0, 0)
        cfg_grid.addWidget(self.cmb_overlay_theme, 0, 1)
        cfg_grid.addWidget(lbl_chime, 0, 2)
        cfg_grid.addWidget(self.cmb_chime, 0, 3)

        cfg_grid.addWidget(lbl_dur, 1, 0)
        cfg_grid.addWidget(self.spn_duration, 1, 1)
        cfg_grid.addWidget(self.chk_show_goals, 1, 2, 1, 2)

        cfg_grid.addWidget(lbl_fg, 2, 0)
        fg_box = QHBoxLayout()
        fg_box.addWidget(self.spn_follow_cur)
        fg_box.addWidget(QLabel("/"))
        fg_box.addWidget(self.spn_follow_tar)
        cfg_grid.addLayout(fg_box, 2, 1)

        cfg_grid.addWidget(lbl_sg, 2, 2)
        sg_box = QHBoxLayout()
        sg_box.addWidget(self.spn_sub_cur)
        sg_box.addWidget(QLabel("/"))
        sg_box.addWidget(self.spn_sub_tar)
        cfg_grid.addLayout(sg_box, 2, 3)

        cfg_grid.addWidget(btn_save_ov, 3, 0, 1, 4)

        layout.addWidget(cfg_frame)
        layout.addStretch()

    # ─────────────────────────────────────────────────────────────────────────
    #  Tab 3: Motor de Voces IA & Puntos del Canal
    # ─────────────────────────────────────────────────────────────────────────

    def _init_ai_voices_tab(self):
        layout = QVBoxLayout(self.tab_ai_voices)
        layout.setSpacing(12)

        tts_cfg = self.storage.data.get("tts", {})

        # Panel superior: Configuración de Voz IA y Probador en Directo
        voice_frame = QFrame()
        voice_frame.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 12px;
            }
        """)
        v_layout = QVBoxLayout(voice_frame)

        top_row = QHBoxLayout()
        self.chk_tts_enabled = QCheckBox("Activar Lectura con Voz IA en el Stream")
        self.chk_tts_enabled.setChecked(bool(tts_cfg.get("enabled", True)))
        self.chk_tts_enabled.setStyleSheet("font-weight: 800; color: #FFFFFF; border: none;")

        lbl_persona = QLabel("Personalidad Voz IA:")
        lbl_persona.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.cmb_persona = QComboBox()
        for pid, pmeta in VOICE_PERSONAS.items():
            self.cmb_persona.addItem(pmeta["name_es"], pid)
        idx_p = self.cmb_persona.findData(tts_cfg.get("persona", "narrador_epico"))
        if idx_p >= 0:
            self.cmb_persona.setCurrentIndex(idx_p)

        lbl_rate = QLabel("Velocidad:")
        lbl_rate.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.sld_rate = QSlider(Qt.Orientation.Horizontal)
        self.sld_rate.setRange(-4, 4)
        self.sld_rate.setValue(int(tts_cfg.get("rate", 1)))
        self.sld_rate.setFixedWidth(110)

        lbl_vol = QLabel("Volumen:")
        lbl_vol.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.sld_vol = QSlider(Qt.Orientation.Horizontal)
        self.sld_vol.setRange(10, 100)
        self.sld_vol.setValue(int(tts_cfg.get("volume", 95)))
        self.sld_vol.setFixedWidth(110)

        top_row.addWidget(self.chk_tts_enabled)
        top_row.addSpacing(14)
        top_row.addWidget(lbl_persona)
        top_row.addWidget(self.cmb_persona)
        top_row.addWidget(lbl_rate)
        top_row.addWidget(self.sld_rate)
        top_row.addWidget(lbl_vol)
        top_row.addWidget(self.sld_vol)
        top_row.addStretch()
        v_layout.addLayout(top_row)

        # Fila de Moderación SafeStream Guard + Guardado
        mod_row = QHBoxLayout()
        self.chk_filter_links = QCheckBox("Bloquear URLs/Links en Voz IA")
        self.chk_filter_links.setChecked(bool(tts_cfg.get("filter_links", True)))
        self.chk_filter_links.setStyleSheet("color: #CBD5E1; font-weight: 600; border: none;")

        lbl_banned = QLabel("Palabras Bloqueadas (coma):")
        lbl_banned.setStyleSheet("color: #CBD5E1; font-weight: 600; border: none;")
        self.inp_banned = QLineEdit(", ".join(tts_cfg.get("banned_words", [])))

        btn_save_tts = QPushButton("Guardar Ajustes IA")
        btn_save_tts.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save_tts.setStyleSheet(self._btn_style("#2563EB", "#1D4ED8"))
        btn_save_tts.clicked.connect(self._save_tts_settings)

        mod_row.addWidget(self.chk_filter_links)
        mod_row.addSpacing(10)
        mod_row.addWidget(lbl_banned)
        mod_row.addWidget(self.inp_banned, 1)
        mod_row.addWidget(btn_save_tts)
        v_layout.addLayout(mod_row)

        # Fila para probar locución IA en directo
        test_row = QHBoxLayout()
        self.inp_test_tts = QLineEdit("¡Hola chat! Bienvenidos al stream, recuerden canjear sus puntos del canal.")
        btn_speak_now = QPushButton("🔊 Hablar con Voz IA + Enviar a OBS")
        btn_speak_now.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_speak_now.setStyleSheet(self._btn_style("#7C3AED", "#6D28D9"))
        btn_speak_now.clicked.connect(self._test_custom_tts)
        test_row.addWidget(self.inp_test_tts, 1)
        test_row.addWidget(btn_speak_now)
        v_layout.addLayout(test_row)

        layout.addWidget(voice_frame)

        # Sección de Recompensas de Puntos del Canal vinculadas a Voces IA
        rw_header = QHBoxLayout()
        rw_lbl = QLabel("Recompensas de Puntos del Canal de Twitch vinculadas a Voces IA")
        rw_lbl.setStyleSheet("font-weight: 800; color: #FFFFFF; font-size: 10.5pt;")
        rw_header.addWidget(rw_lbl)
        rw_header.addStretch()

        self.inp_new_reward_title = QLineEdit()
        self.inp_new_reward_title.setPlaceholderText("Nombre de nueva recompensa (ej: Chiste IA en Directo)")
        self.inp_new_reward_title.setFixedWidth(290)
        self.spn_new_reward_cost = QSpinBox()
        self.spn_new_reward_cost.setRange(50, 500000)
        self.spn_new_reward_cost.setSingleStep(100)
        self.spn_new_reward_cost.setValue(750)
        self.spn_new_reward_cost.setSuffix(" pts")

        btn_add_reward = QPushButton("＋ Agregar Recompensa")
        btn_add_reward.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_reward.setStyleSheet(self._btn_style("#059669", "#047857"))
        btn_add_reward.clicked.connect(self._add_channel_point_reward)

        rw_header.addWidget(self.inp_new_reward_title)
        rw_header.addWidget(self.spn_new_reward_cost)
        rw_header.addWidget(btn_add_reward)
        layout.addLayout(rw_header)

        self.tbl_rewards = QTableWidget(0, 5)
        self.tbl_rewards.setHorizontalHeaderLabels([
            "Recompensa de Puntos del Canal", "Costo (Puntos)", "Voz IA Asignada", "Badge en OBS", "Probar Canje"
        ])
        self._style_table(self.tbl_rewards, stretch_col=0)
        layout.addWidget(self.tbl_rewards, 1)

    # ─────────────────────────────────────────────────────────────────────────
    #  Tab 4: Conexión Twitch en Vivo & Analíticas de Stream
    # ─────────────────────────────────────────────────────────────────────────

    def _init_twitch_tab(self):
        layout = QVBoxLayout(self.tab_twitch)
        layout.setSpacing(12)

        tw_cfg = self.storage.data.get("twitch", {})

        conn_frame = QFrame()
        conn_frame.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        c_layout = QVBoxLayout(conn_frame)

        c_title = QLabel("Conexión en Tiempo Real con tu Canal de Twitch (IRC / EventSub Tags)")
        c_title.setStyleSheet("font-size: 11pt; font-weight: 800; color: #FFFFFF; border: none;")
        c_sub = QLabel(
            "Ingresa el nombre de tu canal de Twitch para escuchar el chat, Bits, Suscripciones, Raids y canjes "
            "de Puntos del Canal en vivo (el Token OAuth es opcional; sin él se conecta en modo lectura instantáneo)."
        )
        c_sub.setStyleSheet("font-size: 9.5pt; color: #94A3B8; border: none;")
        c_layout.addWidget(c_title)
        c_layout.addWidget(c_sub)

        form_row = QHBoxLayout()
        lbl_ch = QLabel("Canal de Twitch:")
        lbl_ch.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.inp_twitch_channel = QLineEdit(tw_cfg.get("channel", ""))
        self.inp_twitch_channel.setPlaceholderText("ej: ibai, auronplay o tu_canal")

        lbl_tok = QLabel("OAuth Token (Opcional):")
        lbl_tok.setStyleSheet("font-weight: 700; color: #E2E8F0; border: none;")
        self.inp_twitch_token = QLineEdit(tw_cfg.get("oauth_token", ""))
        self.inp_twitch_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_twitch_token.setPlaceholderText("oauth:xxxxxxxxxxxxxx")

        self.btn_connect_twitch = QPushButton("Conectar a Twitch")
        self.btn_connect_twitch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect_twitch.setStyleSheet(self._btn_style("#7C3AED", "#6D28D9"))
        self.btn_connect_twitch.clicked.connect(self._toggle_twitch_connection)

        self.lbl_twitch_status = QLabel("Estado: Modo Simulación Local")
        self.lbl_twitch_status.setStyleSheet("font-weight: 700; color: #FBBF24; border: none;")

        form_row.addWidget(lbl_ch)
        form_row.addWidget(self.inp_twitch_channel, 1)
        form_row.addWidget(lbl_tok)
        form_row.addWidget(self.inp_twitch_token, 1)
        form_row.addWidget(self.btn_connect_twitch)
        form_row.addWidget(self.lbl_twitch_status)
        c_layout.addLayout(form_row)

        layout.addWidget(conn_frame)

        # Panel inferior dividido: Analíticas de Sesión + Chat en Vivo
        split_row = QHBoxLayout()
        split_row.setSpacing(12)

        # Tabla Resumen de Analíticas
        analytics_box = QVBoxLayout()
        an_header = QHBoxLayout()
        an_lbl = QLabel("Analíticas Acumuladas del Canal")
        an_lbl.setStyleSheet("font-weight: 800; color: #FFFFFF; font-size: 10.5pt;")
        btn_export = QPushButton("Exportar Reporte CSV")
        btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_export.setStyleSheet(self._btn_style("#059669", "#047857"))
        btn_export.clicked.connect(self._export_analytics_csv)
        an_header.addWidget(an_lbl)
        an_header.addStretch()
        an_header.addWidget(btn_export)
        analytics_box.addLayout(an_header)

        self.tbl_analytics = QTableWidget(0, 2)
        self.tbl_analytics.setHorizontalHeaderLabels(["Métrica de Stream", "Valor Registrado"])
        self._style_table(self.tbl_analytics, stretch_col=0)
        analytics_box.addWidget(self.tbl_analytics, 1)

        # Monitor de Chat en Vivo
        chat_box = QVBoxLayout()
        chat_lbl = QLabel("Monitor de Chat Twitch en Directo")
        chat_lbl.setStyleSheet("font-weight: 800; color: #FFFFFF; font-size: 10.5pt;")
        chat_box.addWidget(chat_lbl)

        self.tbl_chat = QTableWidget(0, 2)
        self.tbl_chat.setHorizontalHeaderLabels(["Espectador", "Mensaje en Chat"])
        self._style_table(self.tbl_chat, stretch_col=1)
        chat_box.addWidget(self.tbl_chat, 1)

        split_row.addLayout(analytics_box, 1)
        split_row.addLayout(chat_box, 1)
        layout.addLayout(split_row, 1)

    # ─────────────────────────────────────────────────────────────────────────
    #  Lógica de Negocio, Eventos, TTS y Actualización de Vistas
    # ─────────────────────────────────────────────────────────────────────────

    def _trigger_simulated_event(self, event_type: str):
        user = random.choice(SAMPLE_VIEWERS)
        if event_type == "follow":
            self._process_stream_event(
                "follow", user, "¡Nuevo seguidor en el canal de Twitch!", 0, "NUEVO SEGUIDOR • TWITCH", use_tts=False
            )
        elif event_type == "sub":
            msg = f"¡{user} se ha suscrito con Prime al canal! ¡Gracias por el apoyo!"
            self._process_stream_event("sub", user, msg, 1, "NUEVO SUSCRIPTOR • TIER 1", use_tts=True)
        elif event_type == "bits":
            msg = f"¡{user} envió 500 Bits! ¡Sigue así con el directo, está increíble!"
            self._process_stream_event("bits", user, msg, 500, "CHEER • 500 BITS", use_tts=True)
        elif event_type == "raid":
            msg = f"¡{user} ha llegado con una Raid de 45 espectadores!"
            self._process_stream_event("raid", user, msg, 45, "RAID EN VIVO • 45 VIEWERS", use_tts=True)
        elif event_type == "channel_points":
            rewards = self.storage.data.get("rewards", [])
            rw = random.choice(rewards) if rewards else {
                "title": "Mensaje con Voz IA", "cost": 500, "persona": "narrador_epico", "alert_badge": "PUNTOS • VOZ IA"
            }
            msg = f"{user} canjeó '{rw['title']}': ¡Saludo épico para todo el chat desde StreamStudio!"
            self._process_stream_event(
                "channel_points",
                user,
                msg,
                int(rw.get("cost", 500)),
                rw.get("alert_badge", "PUNTOS DEL CANAL • VOZ IA"),
                use_tts=True,
                persona=rw.get("persona"),
            )

    def _process_stream_event(
        self,
        event_type: str,
        username: str,
        message: str,
        amount: int = 0,
        badge: str = "ALERTA EN VIVO",
        use_tts: bool = False,
        persona: str | None = None,
    ):
        spoken = ""
        if use_tts:
            spoken = self.tts.speak(message, persona_id=persona)

        evt = self.storage.record_event(
            event_type=event_type,
            username=username,
            message=spoken or message,
            amount=amount,
            tts_used=bool(spoken),
            badge=badge,
        )
        self.overlay_server.push_alert(evt)
        self._refresh_all_views()

    def _replay_event(self, evt: dict):
        if evt.get("tts_used"):
            self.tts.speak(evt.get("message", ""), force=True)
        new_copy = dict(evt)
        new_copy["id"] = f"replay_{random.randint(10000, 99999)}"
        self.overlay_server.push_alert(new_copy)

    def _test_custom_tts(self):
        txt = self.inp_test_tts.text().strip()
        if not txt:
            return
        persona = self.cmb_persona.currentData()
        self._process_stream_event(
            "channel_points",
            "StreamerHost",
            txt,
            500,
            "LOCUCIÓN IA EN DIRECTO",
            use_tts=True,
            persona=persona,
        )

    def _add_channel_point_reward(self):
        title = self.inp_new_reward_title.text().strip()
        if not title:
            QMessageBox.warning(self, "Aviso", "Escribe un título para la recompensa de puntos del canal.")
            return
        cost = self.spn_new_reward_cost.value()
        persona = self.cmb_persona.currentData() or "narrador_epico"

        new_rw = {
            "id": f"rw_{random.randint(1000, 9999)}",
            "title": title,
            "cost": cost,
            "persona": persona,
            "alert_badge": f"PUNTOS ({cost}) • VOZ IA",
            "enabled": True,
        }
        self.storage.data.setdefault("rewards", []).append(new_rw)
        self.storage.save()
        self.inp_new_reward_title.clear()
        self._refresh_rewards_table()

    def _save_overlay_settings(self):
        ov = self.storage.data.setdefault("overlay", {})
        ov["theme"] = self.cmb_overlay_theme.currentData()
        ov["sound_chime"] = self.cmb_chime.currentData()
        ov["duration_sec"] = self.spn_duration.value()
        ov["show_goals_in_overlay"] = self.chk_show_goals.isChecked()
        ov["follower_goal_current"] = self.spn_follow_cur.value()
        ov["follower_goal_target"] = self.spn_follow_tar.value()
        ov["sub_goal_current"] = self.spn_sub_cur.value()
        ov["sub_goal_target"] = self.spn_sub_tar.value()
        self.storage.save()
        QMessageBox.information(
            self,
            "Overlay Actualizado",
            "Los cambios de diseño y metas se han aplicado en tiempo real al servidor de OBS.",
        )

    def _save_tts_settings(self):
        tts_cfg = self.storage.data.setdefault("tts", {})
        tts_cfg["enabled"] = self.chk_tts_enabled.isChecked()
        tts_cfg["persona"] = self.cmb_persona.currentData()
        tts_cfg["rate"] = self.sld_rate.value()
        tts_cfg["volume"] = self.sld_vol.value()
        tts_cfg["filter_links"] = self.chk_filter_links.isChecked()
        words = [w.strip() for w in self.inp_banned.text().split(",") if w.strip()]
        tts_cfg["banned_words"] = words
        self.storage.save()
        QMessageBox.information(
            self,
            "Voces IA y Moderación",
            "La configuración de voz IA y lista negra SafeStream Guard se ha guardado correctamente.",
        )

    def _toggle_twitch_connection(self):
        if self.twitch_bridge._running:
            self.twitch_bridge.disconnect_channel()
            self.btn_connect_twitch.setText("Conectar a Twitch")
            return

        channel = self.inp_twitch_channel.text().strip()
        token = self.inp_twitch_token.text().strip()
        if not channel:
            QMessageBox.warning(self, "Canal requerido", "Ingresa el nombre de usuario del canal de Twitch.")
            return

        tw_cfg = self.storage.data.setdefault("twitch", {})
        tw_cfg["channel"] = channel
        tw_cfg["oauth_token"] = token
        self.storage.save()

        self.twitch_bridge.connect_channel(channel, token)
        self.btn_connect_twitch.setText("Desconectar")

    def _on_twitch_status(self, connected: bool, status_text: str):
        self.lbl_twitch_status.setText(f"● {status_text}")
        self.lbl_twitch_status.setStyleSheet(
            f"font-weight: 700; color: {'#34D399' if connected else '#FBBF24'}; border: none;"
        )
        self.btn_connect_twitch.setText("Desconectar" if connected else "Conectar a Twitch")

    def _on_twitch_chat(self, username: str, text: str):
        self.overlay_server.push_chat(username, text)
        self.tbl_chat.insertRow(0)
        u_item = QTableWidgetItem(username)
        u_item.setForeground(QBrush(QColor("#C084FC")))
        m_item = QTableWidgetItem(text)
        self.tbl_chat.setItem(0, 0, u_item)
        self.tbl_chat.setItem(0, 1, m_item)
        if self.tbl_chat.rowCount() > 50:
            self.tbl_chat.removeRow(50)

    def _on_twitch_event(self, event_type: str, username: str, message: str, amount: int, badge: str):
        use_tts = event_type in ("sub", "bits", "channel_points", "raid")
        self._process_stream_event(event_type, username, message, amount, badge, use_tts=use_tts)

    def _refresh_all_views(self):
        summary = self.storage.get_analytics_summary()
        self.card_follows[1].setText(str(summary["follows"]))
        self.card_subs[1].setText(str(summary["subs"]))
        self.card_bits[1].setText(str(summary["bits_total"]))
        self.card_points[1].setText(str(summary["points_count"]))

        # Sincronizar SpinBoxes de metas
        ov = self.storage.data.get("overlay", {})
        self.spn_follow_cur.setValue(int(ov.get("follower_goal_current", 0)))
        self.spn_sub_cur.setValue(int(ov.get("sub_goal_current", 0)))

        # Poblar tabla de eventos
        events = self.storage.data.get("events", [])
        self.tbl_events.setRowCount(0)
        type_labels = {
            "follow": ("FOLLOW", "#A78BFA"),
            "sub": ("SUSCRIPCIÓN", "#38BDF8"),
            "bits": ("BITS / CHEER", "#FBBF24"),
            "raid": ("RAID", "#F87171"),
            "channel_points": ("PUNTOS IA", "#34D399"),
        }
        for row_idx, evt in enumerate(events[:40]):
            self.tbl_events.insertRow(row_idx)
            self.tbl_events.setItem(row_idx, 0, QTableWidgetItem(evt.get("time", "")))

            t_key = evt.get("type", "follow")
            t_txt, t_col = type_labels.get(t_key, (t_key.upper(), "#E2E8F0"))
            cat_item = QTableWidgetItem(t_txt)
            cat_item.setForeground(QBrush(QColor(t_col)))
            self.tbl_events.setItem(row_idx, 1, cat_item)

            u_item = QTableWidgetItem(evt.get("username", ""))
            u_item.setForeground(QBrush(QColor("#FFFFFF")))
            self.tbl_events.setItem(row_idx, 2, u_item)

            self.tbl_events.setItem(row_idx, 3, QTableWidgetItem(evt.get("message", "")))

            tts_txt = "🔊 Sí" if evt.get("tts_used") else "—"
            self.tbl_events.setItem(row_idx, 4, QTableWidgetItem(tts_txt))

            btn_rep = QPushButton("Repetir en OBS")
            btn_rep.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rep.setStyleSheet(self._btn_style("#334155", "#475569"))
            btn_rep.clicked.connect(lambda _, e=evt: self._replay_event(e))
            self.tbl_events.setCellWidget(row_idx, 5, btn_rep)

        self._refresh_rewards_table()
        self._refresh_analytics_table(summary)

    def _refresh_rewards_table(self):
        rewards = self.storage.data.get("rewards", [])
        self.tbl_rewards.setRowCount(0)
        for idx, rw in enumerate(rewards):
            self.tbl_rewards.insertRow(idx)
            self.tbl_rewards.setItem(idx, 0, QTableWidgetItem(rw.get("title", "")))
            cost_item = QTableWidgetItem(f"{rw.get('cost', 500)} pts")
            cost_item.setForeground(QBrush(QColor("#FBBF24")))
            self.tbl_rewards.setItem(idx, 1, cost_item)

            p_id = rw.get("persona", "narrador_epico")
            p_name = VOICE_PERSONAS.get(p_id, {}).get("name_es", p_id)
            self.tbl_rewards.setItem(idx, 2, QTableWidgetItem(p_name))
            self.tbl_rewards.setItem(idx, 3, QTableWidgetItem(rw.get("alert_badge", "PUNTOS • IA")))

            btn_test = QPushButton("Canjear Prueba IA")
            btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_test.setStyleSheet(self._btn_style("#7C3AED", "#6D28D9"))
            btn_test.clicked.connect(
                lambda _, r=rw: self._process_stream_event(
                    "channel_points",
                    random.choice(SAMPLE_VIEWERS),
                    f"¡Canje de prueba para '{r.get('title')}' activado en vivo!",
                    int(r.get("cost", 500)),
                    r.get("alert_badge", "PUNTOS • VOZ IA"),
                    use_tts=True,
                    persona=r.get("persona"),
                )
            )
            self.tbl_rewards.setCellWidget(idx, 4, btn_test)

    def _refresh_analytics_table(self, summary: dict):
        rows = [
            ("Eventos Totales Procesados", str(summary["total_events"])),
            ("Nuevos Seguidores (Follows)", str(summary["follows"])),
            ("Suscripciones Recibidas", str(summary["subs"])),
            ("Total de Bits / Cheers Donados", f"{summary['bits_total']} Bits"),
            ("Raids Recibidas (Total Viewers)", f"{summary['raids']} Raids ({summary['raiders_total']} espectadores)"),
            ("Canjes de Puntos del Canal con IA", f"{summary['points_count']} canjes ({summary['points_spent']} pts)"),
            ("Locuciones de Voz IA Generadas", str(summary["tts_count"])),
        ]
        for rank, (u_name, cnt) in enumerate(summary.get("top_users", []), start=1):
            rows.append((f"Top Espectador #{rank}", f"{u_name} ({cnt} interacciones)"))

        self.tbl_analytics.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.tbl_analytics.setItem(i, 0, QTableWidgetItem(k))
            val_item = QTableWidgetItem(v)
            val_item.setForeground(QBrush(QColor("#38BDF8")))
            self.tbl_analytics.setItem(i, 1, val_item)

    def _export_analytics_csv(self):
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Exportar Analíticas de StreamStudio", "streamstudio_reporte.csv", "CSV Files (*.csv)"
        )
        if not fpath:
            return
        try:
            events = self.storage.data.get("events", [])
            with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Fecha/Hora", "Tipo", "Usuario Twitch", "Cantidad/Puntos", "Voz IA", "Mensaje"])
                for e in events:
                    writer.writerow([
                        e.get("timestamp", ""),
                        e.get("type", ""),
                        e.get("username", ""),
                        e.get("amount", 0),
                        "Si" if e.get("tts_used") else "No",
                        e.get("message", ""),
                    ])
            QMessageBox.information(self, "Exportación Exitosa", f"Reporte guardado en:\n{fpath}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo exportar el archivo CSV:\n{e}")

    def _copy_url(self, url: str):
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(url)
        QMessageBox.information(
            self,
            "URL Copiada para OBS",
            f"Se ha copiado al portapapeles:\n{url}\n\nPégala en una fuente 'Navegador' (Browser Source) dentro de OBS Studio.",
        )

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers de Estilo y Componentes UI
    # ─────────────────────────────────────────────────────────────────────────

    def _create_metric_card(self, title: str, value: str, subtitle: str, accent_hex: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1E293B;
                border: 1px solid #334155;
                border-top: 3px solid {accent_hex};
                border-radius: 12px;
                padding: 12px;
            }}
        """)
        v = QVBoxLayout(card)
        v.setSpacing(4)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 9.5pt; font-weight: 700; color: #94A3B8; border: none;")
        lbl_val = QLabel(value)
        lbl_val.setStyleSheet(f"font-size: 20pt; font-weight: 900; color: {accent_hex}; border: none;")
        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet("font-size: 8.5pt; color: #64748B; border: none;")
        v.addWidget(lbl_t)
        v.addWidget(lbl_val)
        v.addWidget(lbl_sub)
        return card, lbl_val

    def _style_table(self, table: QTableWidget, stretch_col: int = 0):
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = table.horizontalHeader()
        for col in range(table.columnCount()):
            if col == stretch_col:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            else:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #0F172A;
                alternate-background-color: #162032;
                color: #E2E8F0;
                border: 1px solid #1E293B;
                border-radius: 8px;
                gridline-color: #1E293B;
                font-size: 9.5pt;
            }
            QHeaderView::section {
                background-color: #1E293B;
                color: #94A3B8;
                font-weight: 700;
                padding: 8px;
                border: none;
            }
        """)

    def _btn_style(self, bg: str, hover: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: #FFFFFF;
                font-weight: 700;
                font-size: 9pt;
                padding: 6px 14px;
                border-radius: 7px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #090D16;
                color: #F8FAFC;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 9.5pt;
            }
        """)

    def closeEvent(self, event):
        self.tts.stop_current()
        self.twitch_bridge.disconnect_channel()
        self.overlay_server.stop()
        super().closeEvent(event)
