"""
ui/pages.py
───────────
Páginas del dashboard de StreamStudio:
- DashboardPage (Tarjetas animadas, Gráfico de actividad, Asistente de canal, Quick Settings reales de Twitch y Simulador)
- ActivityPage (Feed en tiempo real con animación de entrada y repetición en OBS)
- OverlaysPage (Browser Sources para OBS, Temas visuales, Vista previa animada y Metas)
- VoicesPage (Personalidades de Voz IA, Velocidad/Volumen, Moderación SafeStream Guard)
- RewardsPage (Recompensas de Puntos del Canal con Voz IA)
- ConnectionPage (Login directo con Twitch OAuth2/Helix, Clave de Transmisión + Sincronización con OBS Studio,
                  Chat en directo bidireccional y Analíticas)
"""

import csv
import webbrowser
from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QLineEdit,
    QComboBox, QSpinBox, QSlider, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QGraphicsOpacityEffect,
)

from . import theme as T
from .theme import EVENT_STYLE, THEME_TILES
from .widgets import (
    TabBar, StatCard, ActivityChart, ToggleSwitch, SelectTile, Mascot, AlertPreview,
    Avatar, make_button, symbol_font,
)
from core.tts_engine import VOICE_PERSONAS


def parse_ts(evt: dict) -> datetime:
    try:
        return datetime.strptime(evt.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.now()


def events_in_range(events: list[dict], key: str) -> list[dict]:
    now = datetime.now()
    if key == "hour":
        return [e for e in events if parse_ts(e) >= now - timedelta(hours=1)]
    if key == "today":
        return [e for e in events if parse_ts(e).date() == now.date()]
    return list(events)


def card_frame(title: str | None = None, subtitle: str | None = None):
    f = QFrame()
    f.setObjectName("flatCard")
    v = QVBoxLayout(f)
    v.setContentsMargins(20, 18, 20, 18)
    v.setSpacing(12)
    if title:
        t = QLabel(title)
        t.setStyleSheet("font-size:11pt; font-weight:800;")
        v.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{T.MUTED}; font-size:9pt;")
        v.addWidget(s)
    return f, v


def label_muted(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"color:{T.MUTED}; font-size:9pt; font-weight:600;")
    return l


class BasePage(QScrollArea):
    def __init__(self, ctx, title: str, subtitle: str = ""):
        super().__init__()
        self.ctx = ctx
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.setWidget(self.body)
        self.root = QVBoxLayout(self.body)
        self.root.setContentsMargins(22, 20, 22, 24)
        self.root.setSpacing(14)
        head = QVBoxLayout()
        head.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-size:19pt; font-weight:800;")
        head.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet(f"color:{T.MUTED}; font-size:9.5pt;")
            head.addWidget(s)
        self.root.addLayout(head)
        ctx.data_changed.connect(self.refresh)

    def refresh(self):
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Dashboard (Estilo StreamElements con Quick Settings real de Twitch)
# ─────────────────────────────────────────────────────────────────────────────

class DashboardPage(BasePage):
    RANGES = [("hour", "Última hora"), ("today", "Hoy"), ("all", "Histórico")]
    METRICS = [
        ("all", "Todos", T.ACCENT), ("follow", "Seguidores", T.PINK), ("sub", "Suscriptores", T.CYAN),
        ("bits", "Bits", T.YELLOW), ("raid", "Raids", T.RED), ("channel_points", "Puntos IA", T.GREEN),
    ]

    def __init__(self, ctx):
        super().__init__(ctx, "Dashboard", "Resumen en vivo e interacción directa con tu canal de Twitch")
        self.range_key = "today"
        self.metric_idx = 0

        banner = QFrame()
        banner.setObjectName("banner")
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(14, 10, 14, 10)
        ic = QLabel("✦")
        ic.setFont(symbol_font(12, True))
        ic.setStyleSheet(f"color:{T.GREEN};")
        self.banner_lbl = QLabel(
            "Conexión Real Twitch Helix activa: actualiza el <b>título y juego de tu stream</b>, "
            "sincroniza tu <b>Clave de Transmisión con OBS</b> y usa comandos <b>!tts</b> en vivo."
        )
        self.banner_lbl.setStyleSheet(f"color:{T.TEXT};")
        bl.addWidget(ic)
        bl.addWidget(self.banner_lbl, 1)
        self.root.addWidget(banner)

        rbar = QHBoxLayout()
        self.range_tabs = TabBar([r[1] for r in self.RANGES], current=1)
        self.range_tabs.changed.connect(self._range_changed)
        rbar.addWidget(self.range_tabs)
        rbar.addStretch()
        self.live_lbl = QLabel("● Datos en vivo")
        self.live_lbl.setStyleSheet(f"color:{T.GREEN}; font-weight:700; font-size:9pt;")
        rbar.addWidget(self.live_lbl)
        self.root.addLayout(rbar)

        grid = QHBoxLayout()
        grid.setSpacing(14)
        self.c_follow = StatCard("Seguidores", "♥", T.PINK)
        self.c_sub = StatCard("Suscriptores", "★", T.ACCENT)
        self.c_bits = StatCard("Bits recibidos", "◆", T.YELLOW)
        self.c_raid = StatCard("Raids (espectadores)", "➤", T.RED)
        for c in (self.c_follow, self.c_sub, self.c_bits, self.c_raid):
            grid.addWidget(c)
        self.root.addLayout(grid)

        body = QHBoxLayout()
        body.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(14)

        chart_card, cv = card_frame()
        self.metric_tabs = TabBar([m[1] for m in self.METRICS])
        self.metric_tabs.changed.connect(self._metric_changed)
        cv.addWidget(self.metric_tabs)
        self.chart = ActivityChart()
        cv.addWidget(self.chart, 1)
        left_col.addWidget(chart_card, 1)

        # Barra de Simulador Rápido debajo del gráfico
        sim_card, sv = card_frame()
        sim_row = QHBoxLayout()
        sim_row.setSpacing(6)
        st = QLabel("SIMULAR:")
        st.setStyleSheet(f"color:{T.MUTED}; font-size:8pt; font-weight:800; letter-spacing:1px;")
        sim_row.addWidget(st)
        for txt_, key, kind in (
            ("♥ Follow", "follow", "Ghost"),
            ("★ Sub", "sub", "Ghost"),
            ("◆ Bits", "bits", "Ghost"),
            ("➤ Raid", "raid", "Ghost"),
            ("♪ Puntos IA", "channel_points", "Purple"),
        ):
            b = make_button(txt_, kind)
            b.clicked.connect(lambda _=False, k=key: ctx.simulate(k))
            sim_row.addWidget(b)
        sv.addLayout(sim_row)
        left_col.addWidget(sim_card)

        body.addLayout(left_col, 1)

        # Columna derecha idéntica a StreamElements: BOT SETTINGS + QUICK SETTINGS
        side = QVBoxLayout()
        side.setSpacing(14)

        bot_card, bv = card_frame()
        bv.setSpacing(8)
        bt = label_muted("BOT SETTINGS")
        bt.setStyleSheet(f"color:{T.MUTED}; font-size:8pt; font-weight:800; letter-spacing:1px;")
        bv.addWidget(bt)
        self.mascot = Mascot()
        bv.addWidget(self.mascot, 0, Qt.AlignmentFlag.AlignHCenter)
        self.bot_text = QLabel()
        self.bot_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bot_text.setWordWrap(True)
        bv.addWidget(self.bot_text)
        row = QHBoxLayout()
        self.btn_connect = make_button("JOIN CHANNEL", "Primary")
        self.btn_connect.clicked.connect(self._connect_clicked)
        btn_mute = make_button("MUTE", "White")
        btn_mute.clicked.connect(ctx.tts.stop_current)
        row.addWidget(self.btn_connect)
        row.addWidget(btn_mute)
        bv.addLayout(row)
        side.addWidget(bot_card)

        # Tarjeta QUICK SETTINGS (Edición real de Título del Stream y Juego en Twitch)
        qs_card, qsv = card_frame()
        qsv.setSpacing(8)
        qst = QLabel("QUICK SETTINGS")
        qst.setStyleSheet(f"color:{T.MUTED}; font-size:8pt; font-weight:800; letter-spacing:1px;")
        qsv.addWidget(qst)

        tw = ctx.storage.data.get("twitch", {})
        qsv.addWidget(label_muted("Stream title"))
        self.inp_qs_title = QLineEdit(tw.get("stream_title", ""))
        self.inp_qs_title.setPlaceholderText("Edita el título de tu stream…")
        qsv.addWidget(self.inp_qs_title)

        qsv.addWidget(label_muted("Game title"))
        self.inp_qs_game = QLineEdit(tw.get("stream_game", ""))
        self.inp_qs_game.setPlaceholderText("Ej: Just Chatting, Valorant…")
        qsv.addWidget(self.inp_qs_game)

        qs_btn_row = QHBoxLayout()
        qs_btn_row.addStretch()
        self.btn_qs_update = make_button("UPDATE", "Primary")
        self.btn_qs_update.clicked.connect(self._update_stream_clicked)
        qs_btn_row.addWidget(self.btn_qs_update)
        qsv.addLayout(qs_btn_row)
        side.addWidget(qs_card)
        side.addStretch()

        side_w = QWidget()
        side_w.setFixedWidth(286)
        side_w.setLayout(side)
        body.addWidget(side_w)
        self.root.addLayout(body)
        self.root.addStretch(1)

        ctx.connection_changed.connect(self._conn_changed)
        ctx.profile_updated.connect(self._on_profile_updated)
        self._conn_changed(ctx.twitch_connected, ctx.twitch_status)
        self.refresh()

    def _range_changed(self, idx):
        self.range_key = self.RANGES[idx][0]
        self.refresh()

    def _metric_changed(self, idx):
        self.metric_idx = idx
        self.refresh(chart_only=True)

    def _connect_clicked(self):
        tw = self.ctx.storage.data.get("twitch", {})
        if tw.get("channel"):
            self.ctx.connect_twitch(tw["channel"], tw.get("oauth_token", ""))
        else:
            self.ctx.go_to_connection()

    def _update_stream_clicked(self):
        title = self.inp_qs_title.text().strip()
        game = self.inp_qs_game.text().strip()
        self.ctx.update_twitch_stream_metadata(title, game)

    def _on_profile_updated(self, snap: dict):
        if snap.get("stream_title") and not self.inp_qs_title.hasFocus():
            self.inp_qs_title.setText(snap["stream_title"])
        if snap.get("stream_game") and not self.inp_qs_game.hasFocus():
            self.inp_qs_game.setText(snap["stream_game"])
        if snap.get("followers_total") is not None:
            self.c_follow.caption.setText(f"Seguidores ({snap['followers_total']:,} en canal)")
        if snap.get("is_live"):
            self.live_lbl.setText(f"● EN VIVO ({snap.get('viewer_count', 0)} espectadores)")
        else:
            self.live_lbl.setText("● Datos en vivo")

    def _conn_changed(self, ok: bool, text: str):
        self.mascot.set_connected(ok)
        if ok:
            self.bot_text.setText(f"El bot está <b>activo</b> en tu chat:<br>{self.ctx.twitch_status}")
            self.btn_connect.setText("PART CHANNEL")
            self.btn_connect.setObjectName("btnDanger")
        else:
            self.bot_text.setText("The bot is currently <b>not</b> in your chat.")
            self.btn_connect.setText("JOIN CHANNEL")
            self.btn_connect.setObjectName("btnPrimary")
        self.btn_connect.style().unpolish(self.btn_connect)
        self.btn_connect.style().polish(self.btn_connect)
        try:
            self.btn_connect.clicked.disconnect()
        except TypeError:
            pass
        self.btn_connect.clicked.connect(self.ctx.disconnect_twitch if ok else self._connect_clicked)

    def _chart_buckets(self, events, key):
        now = datetime.now()
        sec, fmt = {"hour": (300, "%H:%M"), "today": (7200, "%H:%M"), "all": (86400, "%d/%m")}[self.range_key]
        counts = [0.0] * 12
        labels = []
        for i in range(12):
            end = now - timedelta(seconds=(11 - i) * sec)
            labels.append(end.strftime(fmt))
        for e in events:
            if key != "all" and e.get("type") != key:
                continue
            age = (now - parse_ts(e)).total_seconds()
            if age < 0:
                age = 0
            bucket = 11 - int(age // sec)
            if 0 <= bucket < 12:
                counts[bucket] += float(e.get("amount", 0)) if key == "bits" else 1
        return counts, labels

    def refresh(self, chart_only: bool = False):
        events = events_in_range(self.ctx.storage.data.get("events", []), self.range_key)
        key, _, color = self.METRICS[self.metric_idx][0], None, self.METRICS[self.metric_idx][2]
        values, labels = self._chart_buckets(events, key)
        self.chart.set_data(values, labels, color)
        if chart_only:
            return
        follows = sum(1 for e in events if e["type"] == "follow")
        subs = sum(1 for e in events if e["type"] == "sub")
        bits = sum(int(e.get("amount", 0)) for e in events if e["type"] == "bits")
        raids = sum(int(e.get("amount", 0)) for e in events if e["type"] == "raid")
        self.c_follow.set_value(follows)
        self.c_sub.set_value(subs)
        self.c_bits.set_value(bits)
        self.c_raid.set_value(raids)


# ─────────────────────────────────────────────────────────────────────────────
#  Feed de actividad
# ─────────────────────────────────────────────────────────────────────────────

class ActivityPage(BasePage):
    FILTERS = [("all", "Todo"), ("follow", "Seguidores"), ("sub", "Suscripciones"),
               ("bits", "Bits"), ("raid", "Raids"), ("channel_points", "Puntos IA")]

    def __init__(self, ctx):
        super().__init__(ctx, "Feed de actividad", "Cada evento del stream en tiempo real. Repítelo en OBS con un clic.")
        self.filter = "all"
        self._known: set[str] = set()
        self._first = True
        self.tabs = TabBar([f[1] for f in self.FILTERS])
        self.tabs.changed.connect(self._filter_changed)
        self.root.addWidget(self.tabs)
        self.list_l = QVBoxLayout()
        self.list_l.setSpacing(8)
        self.root.addLayout(self.list_l)
        self.empty = QLabel("Aún no hay actividad. Usa el simulador del Dashboard o conecta tu canal.")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"color:{T.MUTED}; padding:50px;")
        self.root.addWidget(self.empty)
        self.root.addStretch(1)
        self._anims = []
        self.refresh()

    def _filter_changed(self, idx):
        self.filter = self.FILTERS[idx][0]
        self._first = True
        self.refresh()

    def _clear(self):
        while self.list_l.count():
            it = self.list_l.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _make_row(self, evt: dict) -> QFrame:
        glyph, color, label = EVENT_STYLE.get(evt.get("type"), ("•", T.MUTED, "Evento"))
        row = QFrame()
        row.setObjectName("row")
        row.setMinimumHeight(66)
        h = QHBoxLayout(row)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(14)
        ic = QLabel(glyph)
        ic.setFixedSize(40, 40)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setFont(symbol_font(14, True))
        ic.setStyleSheet(f"color:{color}; background:rgba(255,255,255,0.05); border-radius:20px;")
        h.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        top = QHBoxLayout()
        top.setSpacing(10)
        name = QLabel(evt.get("username", ""))
        name.setStyleSheet("font-weight:800;")
        tag = QLabel(label.upper())
        tag.setStyleSheet(f"color:{color}; font-size:7.5pt; font-weight:800; letter-spacing:1px;")
        top.addWidget(name)
        top.addWidget(tag)
        top.addStretch()
        col.addLayout(top)
        msg = QLabel(evt.get("message", ""))
        msg.setStyleSheet(f"color:{T.MUTED};")
        msg.setWordWrap(True)
        col.addWidget(msg)
        h.addLayout(col, 1)
        if evt.get("tts_used"):
            p = QLabel("♪ VOZ IA")
            p.setStyleSheet(f"color:{T.GREEN}; background:rgba(52,211,153,0.12); border-radius:8px; "
                            "padding:3px 9px; font-size:8pt; font-weight:800;")
            h.addWidget(p)
        tm = QLabel(evt.get("time", ""))
        tm.setStyleSheet(f"color:{T.MUTED}; font-size:9pt;")
        h.addWidget(tm)
        b = make_button("Repetir en OBS", "Ghost")
        b.clicked.connect(lambda _=False, e=evt: self.ctx.replay(e))
        h.addWidget(b)
        return row

    def _animate_in(self, row: QFrame):
        eff = QGraphicsOpacityEffect(row)
        eff.setOpacity(0)
        row.setGraphicsEffect(eff)
        fade = QPropertyAnimation(eff, b"opacity")
        fade.setDuration(380)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        grow = QPropertyAnimation(row, b"maximumHeight")
        grow.setDuration(420)
        grow.setStartValue(0)
        grow.setEndValue(90)
        grow.setEasingCurve(QEasingCurve.Type.OutCubic)
        g = QParallelAnimationGroup(row)
        g.addAnimation(fade)
        g.addAnimation(grow)

        def done():
            row.setGraphicsEffect(None)
            row.setMaximumHeight(16777215)

        g.finished.connect(done)
        self._anims.append(g)
        g.start()

    def refresh(self):
        events = self.ctx.storage.data.get("events", [])
        if self.filter != "all":
            events = [e for e in events if e.get("type") == self.filter]
        events = events[:60]
        self._clear()
        self.empty.setVisible(not events)
        for evt in events:
            row = self._make_row(evt)
            self.list_l.addWidget(row)
            if not self._first and evt["id"] not in self._known:
                self._animate_in(row)
        self._known = {e["id"] for e in events}
        self._first = False


# ─────────────────────────────────────────────────────────────────────────────
#  Overlays OBS & Metas
# ─────────────────────────────────────────────────────────────────────────────

class OverlaysPage(BasePage):
    def __init__(self, ctx):
        super().__init__(ctx, "Overlays y metas", "Fuentes de navegador para OBS Studio, tema visual y barras de metas.")
        urls, uv = card_frame("Fuentes de navegador (Browser Source)",
                              "En OBS agrega una fuente «Navegador», pega la URL (1280×720). El fondo es transparente.")
        port = ctx.port
        for text, path in (("Overlay completo", "/overlay"), ("Chat en vivo", "/chat"),
                           ("Barra de metas", "/goals?mode=goals")):
            url = f"http://127.0.0.1:{port}{path}"
            r = QHBoxLayout()
            lbl = QLabel(text)
            lbl.setFixedWidth(130)
            lbl.setStyleSheet("font-weight:700;")
            inp = QLineEdit(url)
            inp.setReadOnly(True)
            bc = make_button("Copiar", "Primary")
            bc.clicked.connect(lambda _=False, u=url: ctx.copy_url(u))
            bo = make_button("Probar", "Ghost")
            bo.clicked.connect(lambda _=False, u=url: ctx.open_preview(u))
            r.addWidget(lbl)
            r.addWidget(inp, 1)
            r.addWidget(bc)
            r.addWidget(bo)
            uv.addLayout(r)
        self.root.addWidget(urls)

        mid = QHBoxLayout()
        mid.setSpacing(14)
        theme_card, tv = card_frame("Tema visual", "El cambio se aplica al instante en tu overlay de OBS.")
        tiles = QGridLayout()
        tiles.setSpacing(10)
        self.theme_tiles: dict[str, SelectTile] = {}
        for i, (tid, (name, color)) in enumerate(THEME_TILES.items()):
            t = SelectTile(name, "Acento " + color.upper(), color, swatch=True)
            t.clicked.connect(lambda tid=tid: self._select_theme(tid))
            tiles.addWidget(t, i // 2, i % 2)
            self.theme_tiles[tid] = t
        tv.addLayout(tiles)
        mid.addWidget(theme_card, 1)

        prev_card, pv = card_frame("Vista previa de alerta")
        self.preview = AlertPreview()
        pv.addWidget(self.preview, 1)
        mid.addWidget(prev_card, 1)
        self.root.addLayout(mid)

        beh, bv = card_frame("Comportamiento y metas")
        g = QGridLayout()
        g.setHorizontalSpacing(18)
        g.setVerticalSpacing(12)
        self.cmb_chime = QComboBox()
        for label, key in (("Cristal armónico", "crystal"), ("Arcade 8-bit", "arcade"),
                           ("Fanfarria épica", "fanfare"), ("Sintetizador cyber", "cyber"), ("Sin sonido", "mute")):
            self.cmb_chime.addItem(label, key)
        self.spn_dur = QSpinBox()
        self.spn_dur.setRange(3, 25)
        self.spn_dur.setSuffix(" s")
        self.sw_goals = ToggleSwitch()
        self.spn_fc, self.spn_ft = QSpinBox(), QSpinBox()
        self.spn_sc, self.spn_st = QSpinBox(), QSpinBox()
        for s in (self.spn_fc, self.spn_ft, self.spn_sc, self.spn_st):
            s.setRange(0, 1000000)
        g.addWidget(label_muted("Sonido de alerta"), 0, 0)
        g.addWidget(self.cmb_chime, 1, 0)
        g.addWidget(label_muted("Duración en pantalla"), 0, 1)
        g.addWidget(self.spn_dur, 1, 1)
        g.addWidget(label_muted("Mostrar metas en el overlay"), 0, 2)
        g.addWidget(self.sw_goals, 1, 2, Qt.AlignmentFlag.AlignLeft)
        g.addWidget(label_muted("Meta de seguidores (actual / objetivo)"), 2, 0, 1, 2)
        fr = QHBoxLayout()
        fr.addWidget(self.spn_fc)
        fr.addWidget(QLabel("/"))
        fr.addWidget(self.spn_ft)
        g.addLayout(fr, 3, 0, 1, 2)
        g.addWidget(label_muted("Meta de suscriptores (actual / objetivo)"), 2, 2)
        sr = QHBoxLayout()
        sr.addWidget(self.spn_sc)
        sr.addWidget(QLabel("/"))
        sr.addWidget(self.spn_st)
        g.addLayout(sr, 3, 2)
        bv.addLayout(g)
        self.root.addWidget(beh)
        self.root.addStretch(1)

        self._sync_from_storage()
        self.cmb_chime.currentIndexChanged.connect(self._apply)
        for w in (self.spn_dur, self.spn_fc, self.spn_ft, self.spn_sc, self.spn_st):
            w.valueChanged.connect(self._apply)
        self.sw_goals.toggled.connect(self._apply)

    def _sync_from_storage(self):
        ov = self.ctx.storage.data["overlay"]
        widgets = (self.cmb_chime, self.spn_dur, self.spn_fc, self.spn_ft, self.spn_sc, self.spn_st)
        for w in widgets:
            w.blockSignals(True)
        self.cmb_chime.setCurrentIndex(max(0, self.cmb_chime.findData(ov.get("sound_chime", "crystal"))))
        self.spn_dur.setValue(int(ov.get("duration_sec", 6)))
        self.spn_fc.setValue(int(ov.get("follower_goal_current", 0)))
        self.spn_ft.setValue(max(1, int(ov.get("follower_goal_target", 100))))
        self.spn_sc.setValue(int(ov.get("sub_goal_current", 0)))
        self.spn_st.setValue(max(1, int(ov.get("sub_goal_target", 25))))
        for w in widgets:
            w.blockSignals(False)
        self.sw_goals.set_checked_silent(bool(ov.get("show_goals_in_overlay", True)))
        theme = ov.get("theme", "twitch_purple")
        for tid, tile in self.theme_tiles.items():
            tile.set_selected(tid == theme, animate=False)
        self.preview.set_accent(THEME_TILES.get(theme, THEME_TILES["twitch_purple"])[1])

    def _select_theme(self, tid: str):
        for k, t in self.theme_tiles.items():
            t.set_selected(k == tid)
        self.preview.set_accent(THEME_TILES[tid][1])
        self.ctx.storage.data["overlay"]["theme"] = tid
        self.ctx.autosave()

    def _apply(self, *_):
        ov = self.ctx.storage.data["overlay"]
        ov["sound_chime"] = self.cmb_chime.currentData()
        ov["duration_sec"] = self.spn_dur.value()
        ov["show_goals_in_overlay"] = self.sw_goals.isChecked()
        ov["follower_goal_current"] = self.spn_fc.value()
        ov["follower_goal_target"] = max(1, self.spn_ft.value())
        ov["sub_goal_current"] = self.spn_sc.value()
        ov["sub_goal_target"] = max(1, self.spn_st.value())
        self.ctx.autosave()

    def refresh(self):
        ov = self.ctx.storage.data["overlay"]
        for w, k in ((self.spn_fc, "follower_goal_current"), (self.spn_sc, "sub_goal_current")):
            w.blockSignals(True)
            w.setValue(int(ov.get(k, 0)))
            w.blockSignals(False)


# ─────────────────────────────────────────────────────────────────────────────
#  Voces IA
# ─────────────────────────────────────────────────────────────────────────────

PERSONA_DESC = {
    "narrador_epico": "Tono grave y cinematográfico para momentos grandes.",
    "comentarista_hype": "Rápido y enérgico, ideal para raids y bits.",
    "ia_cyber": "Estilo sintético: «Sistema IA informa…».",
    "asistente_suave": "Calmado y amable para recordatorios del canal.",
}


class VoicesPage(BasePage):
    def __init__(self, ctx):
        super().__init__(ctx, "Voces IA", "Lectura por voz de alertas y puntos del canal, con moderación integrada.")
        cfg = ctx.storage.data["tts"]

        top, tv = card_frame()
        row = QHBoxLayout()
        sw_col = QVBoxLayout()
        sw_col.setSpacing(0)
        a = QLabel("Lectura con Voz IA en el stream")
        a.setStyleSheet("font-size:11pt; font-weight:800;")
        b = label_muted("Cuando está desactivada, las alertas solo se muestran visualmente.")
        sw_col.addWidget(a)
        sw_col.addWidget(b)
        row.addLayout(sw_col, 1)
        self.sw_enabled = ToggleSwitch(bool(cfg.get("enabled", True)))
        row.addWidget(self.sw_enabled)
        tv.addLayout(row)
        self.root.addWidget(top)

        pc, pv = card_frame("Personalidad de voz")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.tiles: dict[str, SelectTile] = {}
        for i, (pid, meta) in enumerate(VOICE_PERSONAS.items()):
            t = SelectTile(meta["name_es"], PERSONA_DESC.get(pid, ""), T.PURPLE)
            t.clicked.connect(lambda pid=pid: self._select_persona(pid))
            grid.addWidget(t, i // 2, i % 2)
            self.tiles[pid] = t
        pv.addLayout(grid)
        self.root.addWidget(pc)

        mix, mv = card_frame("Ajustes de locución")
        sl = QGridLayout()
        sl.setHorizontalSpacing(24)
        self.sld_rate = QSlider(Qt.Orientation.Horizontal)
        self.sld_rate.setRange(-4, 4)
        self.sld_vol = QSlider(Qt.Orientation.Horizontal)
        self.sld_vol.setRange(10, 100)
        self.lbl_rate, self.lbl_vol = QLabel(), QLabel()
        for l in (self.lbl_rate, self.lbl_vol):
            l.setStyleSheet(f"color:{T.ACCENT}; font-weight:800;")
        sl.addWidget(label_muted("Velocidad"), 0, 0)
        sl.addWidget(self.lbl_rate, 0, 1, Qt.AlignmentFlag.AlignRight)
        sl.addWidget(self.sld_rate, 1, 0, 1, 2)
        sl.addWidget(label_muted("Volumen"), 0, 2)
        sl.addWidget(self.lbl_vol, 0, 3, Qt.AlignmentFlag.AlignRight)
        sl.addWidget(self.sld_vol, 1, 2, 1, 2)
        mv.addLayout(sl)
        self.root.addWidget(mix)

        mod, modv = card_frame("Moderación SafeStream Guard",
                               "Filtra enlaces, spam repetitivo y palabras prohibidas antes de hablar.")
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Bloquear URLs en la voz"))
        r2.addStretch()
        self.sw_links = ToggleSwitch(bool(cfg.get("filter_links", True)))
        r2.addWidget(self.sw_links)
        modv.addLayout(r2)
        modv.addWidget(label_muted("Palabras bloqueadas (separadas por coma)"))
        self.inp_banned = QLineEdit(", ".join(cfg.get("banned_words", [])))
        modv.addWidget(self.inp_banned)
        self.root.addWidget(mod)

        test, tsv = card_frame("Probador de voz", "Se reproduce con la voz IA y aparece en tu overlay de OBS.")
        tr = QHBoxLayout()
        self.inp_test = QLineEdit("¡Hola chat! Bienvenidos al stream, no olviden canjear sus puntos del canal.")
        bt = make_button("♪  Hablar y enviar a OBS", "Purple")
        bt.clicked.connect(self._speak)
        tr.addWidget(self.inp_test, 1)
        tr.addWidget(bt)
        tsv.addLayout(tr)
        self.root.addWidget(test)
        self.root.addStretch(1)

        self.sld_rate.setValue(int(cfg.get("rate", 1)))
        self.sld_vol.setValue(int(cfg.get("volume", 95)))
        self._update_labels()
        self._mark_persona(cfg.get("persona", "narrador_epico"), animate=False)

        self.sw_enabled.toggled.connect(self._apply)
        self.sw_links.toggled.connect(self._apply)
        self.sld_rate.valueChanged.connect(self._apply)
        self.sld_vol.valueChanged.connect(self._apply)
        self.inp_banned.editingFinished.connect(self._apply)

    def _update_labels(self):
        r = self.sld_rate.value()
        self.lbl_rate.setText(f"{'+' if r > 0 else ''}{r}")
        self.lbl_vol.setText(f"{self.sld_vol.value()}%")

    def _mark_persona(self, pid, animate=True):
        for k, t in self.tiles.items():
            t.set_selected(k == pid, animate)

    def _select_persona(self, pid):
        self._mark_persona(pid)
        self.ctx.storage.data["tts"]["persona"] = pid
        self.ctx.autosave()

    def _apply(self, *_):
        cfg = self.ctx.storage.data["tts"]
        cfg["enabled"] = self.sw_enabled.isChecked()
        cfg["filter_links"] = self.sw_links.isChecked()
        cfg["rate"] = self.sld_rate.value()
        cfg["volume"] = self.sld_vol.value()
        cfg["banned_words"] = [w.strip() for w in self.inp_banned.text().split(",") if w.strip()]
        self._update_labels()
        self.ctx.autosave()

    def _speak(self):
        txt = self.inp_test.text().strip()
        if txt:
            persona = self.ctx.storage.data["tts"].get("persona")
            self.ctx.process_event("channel_points", "StreamerHost", txt, 500,
                                   "LOCUCIÓN IA EN DIRECTO", use_tts=True, persona=persona, force_tts=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Recompensas de puntos del canal
# ─────────────────────────────────────────────────────────────────────────────

class RewardsPage(BasePage):
    def __init__(self, ctx):
        super().__init__(ctx, "Recompensas de puntos del canal",
                         "Vincula canjes de Twitch con voces IA y alertas en pantalla.")
        add, av = card_frame("Nueva recompensa")
        r = QHBoxLayout()
        self.inp_title = QLineEdit()
        self.inp_title.setPlaceholderText("Ej: Chiste con Voz IA en directo")
        self.spn_cost = QSpinBox()
        self.spn_cost.setRange(50, 500000)
        self.spn_cost.setSingleStep(100)
        self.spn_cost.setValue(750)
        self.spn_cost.setSuffix(" pts")
        b = make_button("＋  Agregar", "Primary")
        b.clicked.connect(self._add)
        self.inp_title.returnPressed.connect(self._add)
        r.addWidget(self.inp_title, 1)
        r.addWidget(self.spn_cost)
        r.addWidget(b)
        av.addLayout(r)
        self.root.addWidget(add)
        self.list_l = QVBoxLayout()
        self.list_l.setSpacing(8)
        self.root.addLayout(self.list_l)
        self.root.addStretch(1)
        self._build()

    def _build(self):
        while self.list_l.count():
            it = self.list_l.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for rw in self.ctx.storage.data.get("rewards", []):
            self.list_l.addWidget(self._row(rw))

    def _row(self, rw: dict) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        row.setMinimumHeight(68)
        h = QHBoxLayout(row)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(14)
        ic = QLabel("♪")
        ic.setFixedSize(40, 40)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setFont(symbol_font(14, True))
        ic.setStyleSheet(f"color:{T.GREEN}; background:rgba(52,211,153,0.12); border-radius:20px;")
        h.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(rw.get("title", ""))
        t.setStyleSheet("font-weight:800;")
        persona = VOICE_PERSONAS.get(rw.get("persona"), {}).get("name_es", rw.get("persona", ""))
        s = label_muted(f"Voz: {persona}  •  {rw.get('alert_badge', '')}")
        col.addWidget(t)
        col.addWidget(s)
        h.addLayout(col, 1)
        cost = QLabel(f"{rw.get('cost', 500):,} pts")
        cost.setStyleSheet(f"color:{T.YELLOW}; background:rgba(251,191,36,0.12); border-radius:8px; "
                           "padding:4px 10px; font-weight:800;")
        h.addWidget(cost)
        sw = ToggleSwitch(bool(rw.get("enabled", True)))
        sw.toggled.connect(lambda on, r=rw: self._toggle(r, on))
        h.addWidget(sw)
        bt = make_button("Probar canje", "Purple")
        bt.clicked.connect(lambda _=False, r=rw: self._test(r))
        h.addWidget(bt)
        bd = make_button("Eliminar", "Danger")
        bd.clicked.connect(lambda _=False, r=rw: self._delete(r))
        h.addWidget(bd)
        return row

    def _toggle(self, rw, on):
        rw["enabled"] = on
        self.ctx.autosave()

    def _test(self, rw):
        from random import choice
        from ui.main_window import SAMPLE_VIEWERS
        self.ctx.process_event("channel_points", choice(SAMPLE_VIEWERS),
                               f"¡Canje de prueba de '{rw.get('title')}' activado en vivo!",
                               int(rw.get("cost", 500)), rw.get("alert_badge", "PUNTOS • VOZ IA"),
                               use_tts=True, persona=rw.get("persona"))

    def _delete(self, rw):
        rewards = self.ctx.storage.data.get("rewards", [])
        if rw in rewards:
            rewards.remove(rw)
        self.ctx.storage.save()
        self._build()
        self.ctx.toast("Recompensa eliminada", T.RED)

    def _add(self):
        title = self.inp_title.text().strip()
        if not title:
            self.ctx.toast("Escribe un nombre para la recompensa", T.YELLOW)
            return
        cost = self.spn_cost.value()
        self.ctx.storage.data.setdefault("rewards", []).append({
            "id": f"rw_{int(datetime.now().timestamp())}",
            "title": title,
            "cost": cost,
            "persona": self.ctx.storage.data["tts"].get("persona", "narrador_epico"),
            "alert_badge": f"PUNTOS ({cost}) • VOZ IA",
            "enabled": True,
        })
        self.ctx.storage.save()
        self.inp_title.clear()
        self._build()
        self.ctx.toast("Recompensa agregada")


# ─────────────────────────────────────────────────────────────────────────────
#  Cuenta de Twitch (OAuth 2.0 + Helix API), Clave de Transmisión & Analíticas
# ─────────────────────────────────────────────────────────────────────────────

class ConnectionPage(BasePage):
    def __init__(self, ctx):
        super().__init__(
            ctx,
            "Cuenta Twitch, Clave de Transmisión y Analíticas",
            "Inicia sesión directo en tu canal de Twitch, sincroniza tu Clave de Transmisión con OBS y chatea en vivo.",
        )
        tw = ctx.storage.data["twitch"]

        # ── 1. Tarjeta de Login Directo con Twitch (OAuth2 + Helix API) ───────
        conn, cv = card_frame(
            "1. Inicio de Sesión Directo con tu Cuenta de Twitch (OAuth 2.0 + Helix API)",
            "Conecta tu cuenta con Token OAuth o autorización en navegador para editar el título/juego de tu stream, "
            "cargar tu foto de perfil real, detectar seguidores y enviar mensajes al chat.",
        )

        # Resumen visual de perfil autenticado
        prof_row = QHBoxLayout()
        prof_row.setSpacing(14)
        self.prof_avatar = Avatar(52)
        if tw.get("channel"):
            self.prof_avatar.set_name(tw["channel"])
        prof_row.addWidget(self.prof_avatar)

        prof_info = QVBoxLayout()
        prof_info.setSpacing(2)
        self.lbl_prof_name = QLabel(tw.get("display_name") or tw.get("channel") or "Cuenta no vinculada")
        self.lbl_prof_name.setStyleSheet("font-size:13pt; font-weight:800;")
        self.lbl_prof_meta = QLabel("Vincula tu cuenta vía OAuth o navegador.")
        self.lbl_prof_meta.setWordWrap(True)
        self.lbl_prof_meta.setStyleSheet(f"color:{T.MUTED}; font-size:9pt;")
        prof_info.addWidget(self.lbl_prof_name)
        prof_info.addWidget(self.lbl_prof_meta)
        prof_row.addLayout(prof_info, 1)

        btn_browser_oauth = make_button("🔗 Login Web", "Purple")
        btn_browser_oauth.clicked.connect(self._open_browser_oauth)
        prof_row.addWidget(btn_browser_oauth)

        btn_get_tok = make_button("🔑 Token", "Ghost")
        btn_get_tok.clicked.connect(lambda: webbrowser.open("https://twitchtokengenerator.com/"))
        prof_row.addWidget(btn_get_tok)

        self.btn_signout = make_button("Salir", "Danger")
        self.btn_signout.clicked.connect(self.ctx.logout_twitch)
        prof_row.addWidget(self.btn_signout)
        cv.addLayout(prof_row)

        # Formulario de credenciales
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        form.addWidget(label_muted("Canal de Twitch"), 0, 0)
        form.addWidget(label_muted("Token OAuth (oauth:xxxx)"), 0, 1)
        form.addWidget(label_muted("Client ID (Autodetectado)"), 0, 2)

        self.inp_channel = QLineEdit(tw.get("channel", ""))
        self.inp_channel.setPlaceholderText("ej: tu_canal")

        self.inp_token = QLineEdit(tw.get("oauth_token", ""))
        self.inp_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_token.setPlaceholderText("Pega tu Token OAuth…")

        self.inp_client_id = QLineEdit(tw.get("client_id", ""))
        self.inp_client_id.setPlaceholderText("Opcional / Autodetectado")

        form.addWidget(self.inp_channel, 1, 0)
        form.addWidget(self.inp_token, 1, 1)
        form.addWidget(self.inp_client_id, 1, 2)
        cv.addLayout(form)

        act_row = QHBoxLayout()
        self.status = QLabel()
        act_row.addWidget(self.status, 1)

        act_row.addWidget(label_muted("Auto-conectar"))
        self.sw_auto = ToggleSwitch(bool(tw.get("auto_connect", True)))
        self.sw_auto.toggled.connect(self._auto)
        act_row.addWidget(self.sw_auto)

        btn_sync_api = make_button("↻ Sincronizar Twitch", "Ghost")
        btn_sync_api.clicked.connect(lambda: self.ctx.authenticate_and_sync(
            self.inp_token.text().strip(),
            self.inp_client_id.text().strip(),
            self.inp_channel.text().strip(),
        ))
        act_row.addWidget(btn_sync_api)

        self.btn = make_button("Conectar Cuenta", "Primary")
        self.btn.clicked.connect(self._click)
        act_row.addWidget(self.btn)
        cv.addLayout(act_row)
        self.root.addWidget(conn)

        # ── 2. Tarjeta de Clave de Transmisión (Stream Key) & OBS Studio ─────
        sk_card, skv = card_frame(
            "2. Clave de Transmisión (Stream Key) y Sincronización Directa con OBS Studio",
            "Guarda tu clave de transmisión (live_...) o impórtala/sincronízala directamente con el perfil de OBS Studio de tu PC.",
        )
        sk_grid = QGridLayout()
        sk_grid.setHorizontalSpacing(12)
        sk_grid.setVerticalSpacing(8)
        sk_grid.addWidget(label_muted("Clave de Transmisión de Twitch (Stream Key)"), 0, 0)
        sk_grid.addWidget(label_muted("Servidor RTMP de Transmisión"), 0, 1)

        self.inp_stream_key = QLineEdit(tw.get("stream_key", ""))
        self.inp_stream_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_stream_key.setPlaceholderText("live_xxxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxx")
        self.inp_stream_key.editingFinished.connect(self._save_stream_key)

        self.inp_rtmp = QLineEdit(tw.get("rtmp_server", "rtmp://live.twitch.tv/app/"))
        self.inp_rtmp.editingFinished.connect(self._save_stream_key)

        sk_grid.addWidget(self.inp_stream_key, 1, 0)
        sk_grid.addWidget(self.inp_rtmp, 1, 1)
        skv.addLayout(sk_grid)

        sk_btns = QHBoxLayout()
        btn_toggle_sk = make_button("👁 Mostrar", "Ghost")
        btn_toggle_sk.clicked.connect(self._toggle_stream_key_visibility)
        sk_btns.addWidget(btn_toggle_sk)

        btn_copy_sk = make_button("Copiar Clave", "Ghost")
        btn_copy_sk.clicked.connect(self._copy_stream_key)
        sk_btns.addWidget(btn_copy_sk)

        btn_import_obs = make_button("📥 Importar de OBS", "Ghost")
        btn_import_obs.clicked.connect(self._import_from_obs)
        sk_btns.addWidget(btn_import_obs)

        btn_export_obs = make_button("📤 Enviar a OBS Studio", "Primary")
        btn_export_obs.clicked.connect(self._export_to_obs)
        sk_btns.addWidget(btn_export_obs)

        btn_twitch_dash = make_button("Panel Twitch ↗", "Ghost")
        btn_twitch_dash.clicked.connect(lambda: webbrowser.open("https://dashboard.twitch.tv/settings/stream"))
        sk_btns.addWidget(btn_twitch_dash)
        sk_btns.addStretch()
        skv.addLayout(sk_btns)
        self.root.addWidget(sk_card)

        # ── 3. Panel inferior: Analíticas + Chat en Directo Bidireccional ─────
        split = QHBoxLayout()
        split.setSpacing(14)
        an, av = card_frame()
        hh = QHBoxLayout()
        t = QLabel("Analíticas acumuladas")
        t.setStyleSheet("font-size:11pt; font-weight:800;")
        hh.addWidget(t)
        hh.addStretch()
        be = make_button("Exportar CSV", "Success")
        be.clicked.connect(self._export)
        hh.addWidget(be)
        av.addLayout(hh)
        self.tbl_an = QTableWidget(0, 2)
        self.tbl_an.setHorizontalHeaderLabels(["Métrica", "Valor"])
        self._style_table(self.tbl_an, 0)
        av.addWidget(self.tbl_an, 1)
        split.addWidget(an, 1)

        chat, chv = card_frame("Chat de Twitch en directo (Lectura y Envío)")
        self.tbl_chat = QTableWidget(0, 2)
        self.tbl_chat.setHorizontalHeaderLabels(["Espectador", "Mensaje"])
        self._style_table(self.tbl_chat, 1)
        chv.addWidget(self.tbl_chat, 1)

        send_row = QHBoxLayout()
        self.inp_chat_msg = QLineEdit()
        self.inp_chat_msg.setPlaceholderText("Escribe un mensaje real para tu chat de Twitch (o !tts Hola)…")
        self.inp_chat_msg.returnPressed.connect(self._send_chat)
        btn_send_chat = make_button("Enviar al Chat", "Purple")
        btn_send_chat.clicked.connect(self._send_chat)
        send_row.addWidget(self.inp_chat_msg, 1)
        send_row.addWidget(btn_send_chat)
        chv.addLayout(send_row)

        split.addWidget(chat, 1)
        self.root.addLayout(split, 1)

        ctx.connection_changed.connect(self._conn_changed)
        ctx.chat_received.connect(self._chat)
        ctx.profile_updated.connect(self._on_profile_updated)
        self._conn_changed(ctx.twitch_connected, ctx.twitch_status)
        self.refresh()

    def _style_table(self, tbl: QTableWidget, stretch_col: int):
        tbl.setMinimumHeight(240)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tbl.setAlternatingRowColors(True)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        hdr = tbl.horizontalHeader()
        for c in range(tbl.columnCount()):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch if c == stretch_col
                                     else QHeaderView.ResizeMode.ResizeToContents)

    def _open_browser_oauth(self):
        cid = self.inp_client_id.text().strip() or self.ctx.storage.data["twitch"].get("client_id", "")
        self.ctx.start_browser_oauth(cid)

    def _click(self):
        if self.ctx.twitch_connected:
            self.ctx.disconnect_twitch()
        else:
            tok = self.inp_token.text().strip()
            cid = self.inp_client_id.text().strip()
            ch = self.inp_channel.text().strip()
            if tok:
                self.ctx.authenticate_and_sync(tok, cid, ch)
            else:
                self.ctx.connect_twitch(ch, "")

    def _auto(self, on):
        self.ctx.storage.data["twitch"]["auto_connect"] = on
        self.ctx.autosave()

    def _save_stream_key(self):
        tw = self.ctx.storage.data["twitch"]
        tw["stream_key"] = self.inp_stream_key.text().strip()
        tw["rtmp_server"] = self.inp_rtmp.text().strip() or "rtmp://live.twitch.tv/app/"
        self.ctx.storage.save()

    def _toggle_stream_key_visibility(self):
        if self.inp_stream_key.echoMode() == QLineEdit.EchoMode.Password:
            self.inp_stream_key.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.inp_stream_key.setEchoMode(QLineEdit.EchoMode.Password)

    def _copy_stream_key(self):
        val = self.inp_stream_key.text().strip()
        if not val:
            self.ctx.toast("No hay clave de transmisión configurada", T.YELLOW)
            return
        from PyQt6.QtGui import QGuiApplication
        cb = QGuiApplication.clipboard()
        if cb:
            cb.setText(val)
        self.ctx.toast("Clave de transmisión copiada al portapapeles", T.ACCENT)

    def _import_from_obs(self):
        from core.twitch_client import TwitchHelixClient
        ok, key, server, prof = TwitchHelixClient.import_obs_stream_key()
        if ok:
            self.inp_stream_key.setText(key)
            self.inp_rtmp.setText(server)
            self._save_stream_key()
            self.ctx.toast(f"Clave importada desde OBS Studio (Perfil: {prof})", T.GREEN)
        else:
            self.ctx.toast("No se encontró una clave guardada en los perfiles de OBS Studio", T.YELLOW)

    def _export_to_obs(self):
        from core.twitch_client import TwitchHelixClient
        self._save_stream_key()
        ok, msg = TwitchHelixClient.export_obs_stream_key(
            self.inp_stream_key.text().strip(),
            self.inp_rtmp.text().strip(),
        )
        self.ctx.toast(msg, T.GREEN if ok else T.YELLOW)

    def _send_chat(self):
        txt = self.inp_chat_msg.text().strip()
        if not txt:
            return
        if self.ctx.send_chat_message(txt):
            self.inp_chat_msg.clear()

    def _on_profile_updated(self, snap: dict):
        if snap.get("login"):
            self.inp_channel.setText(snap["login"])
        if snap.get("client_id"):
            self.inp_client_id.setText(snap["client_id"])
        if snap.get("token"):
            self.inp_token.setText(snap["token"])
        if snap.get("stream_key"):
            self.inp_stream_key.setText(snap["stream_key"])

        disp = snap.get("display_name") or snap.get("login") or "Canal conectado"
        self.prof_avatar.set_name(disp)
        if snap.get("avatar_bytes"):
            self.prof_avatar.set_image_bytes(snap["avatar_bytes"])

        btype = (snap.get("broadcaster_type") or "streamer").upper()
        flw = snap.get("followers_total")
        flw_txt = f"{flw:,} seguidores" if flw is not None else "Seguidores sincronizados"
        live_txt = f"EN VIVO ({snap.get('viewer_count', 0)} viewers)" if snap.get("is_live") else "OFFLINE"
        self.lbl_prof_name.setText(f"{disp}  (@{snap.get('login', '')})")
        self.lbl_prof_meta.setText(
            f"ID: {snap.get('user_id', '—')}  •  Rango: {btype}  •  {flw_txt}  •  Estado: {live_txt}"
        )

    def _conn_changed(self, ok: bool, text: str):
        self.btn.setText("Desconectar" if ok else "Conectar Canal")
        color = T.GREEN if ok else T.YELLOW
        self.status.setText(f"● {text}")
        self.status.setStyleSheet(f"color:{color}; font-weight:700;")

    def _chat(self, user: str, text: str):
        self.tbl_chat.insertRow(0)
        u = QTableWidgetItem(user)
        u.setForeground(Qt.GlobalColor.magenta)
        self.tbl_chat.setItem(0, 0, u)
        self.tbl_chat.setItem(0, 1, QTableWidgetItem(text))
        while self.tbl_chat.rowCount() > 60:
            self.tbl_chat.removeRow(self.tbl_chat.rowCount() - 1)

    def refresh(self):
        s = self.ctx.storage.get_analytics_summary()
        rows = [
            ("Eventos totales", str(s["total_events"])),
            ("Nuevos seguidores (sesión)", str(s["follows"])),
            ("Suscripciones", str(s["subs"])),
            ("Bits donados", f"{s['bits_total']:,}"),
            ("Raids", f"{s['raids']} ({s['raiders_total']} espectadores)"),
            ("Canjes con IA", f"{s['points_count']} ({s['points_spent']:,} pts)"),
            ("Locuciones de voz IA", str(s["tts_count"])),
        ]
        for i, (u, c) in enumerate(s.get("top_users", []), 1):
            rows.append((f"Top espectador #{i}", f"{u} ({c})"))
        self.tbl_an.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.tbl_an.setItem(i, 0, QTableWidgetItem(k))
            it = QTableWidgetItem(v)
            it.setForeground(Qt.GlobalColor.cyan)
            self.tbl_an.setItem(i, 1, it)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar analíticas", "streamstudio_reporte.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["Fecha/Hora", "Tipo", "Usuario", "Cantidad", "Voz IA", "Mensaje"])
                for e in self.ctx.storage.data.get("events", []):
                    w.writerow([e.get("timestamp", ""), e.get("type", ""), e.get("username", ""),
                                e.get("amount", 0), "Si" if e.get("tts_used") else "No", e.get("message", "")])
            self.ctx.toast("Reporte CSV exportado")
        except Exception as ex:
            self.ctx.toast(f"No se pudo exportar: {ex}", T.RED)
