"""
ui/widgets.py
─────────────
Componentes visuales animados reutilizables de StreamStudio:
Sidebar con indicador deslizante y grupos colapsables, transiciones de página, tarjetas con
conteo animado, gráfico de actividad animado, switch, tiles seleccionables, mascota de estado,
vista previa de alerta y notificaciones (toasts).
"""

import math
from datetime import datetime

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QPoint, QRect,
    QVariantAnimation, pyqtProperty, pyqtSignal, QTimer, QRectF, QPointF,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QPixmap, QPainterPath,
)
from PyQt6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QAbstractButton,
)

from . import theme as T


def blend(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(c1.red() + (c2.red() - c1.red()) * t),
        int(c1.green() + (c2.green() - c1.green()) * t),
        int(c1.blue() + (c2.blue() - c1.blue()) * t),
        int(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


def make_button(text: str, kind: str = "Primary") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("btn" + kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def symbol_font(size: float = 13, bold: bool = False) -> QFont:
    f = QFont(T.SYMBOL_FONT)
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


# ─────────────────────────────────────────────────────────────────────────────
#  Transición de páginas (desplazamiento + fundido)
# ─────────────────────────────────────────────────────────────────────────────

class AnimatedStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._group = None
        self._widget = None

    def _finish(self):
        if self._widget is not None:
            self._widget.setGraphicsEffect(None)
            self._widget = None

    def slide_to(self, index: int):
        cur = self.currentIndex()
        if index == cur:
            return
        if self._group is not None:
            self._group.stop()
            self._finish()
        direction = 1 if index > cur else -1
        super().setCurrentIndex(index)
        page = self.currentWidget()
        eff = QGraphicsOpacityEffect(page)
        eff.setOpacity(0.0)
        page.setGraphicsEffect(eff)
        self._widget = page

        fade = QPropertyAnimation(eff, b"opacity")
        fade.setDuration(340)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        slide = QPropertyAnimation(page, b"pos")
        slide.setDuration(420)
        slide.setStartValue(QPoint(direction * 56, 0))
        slide.setEndValue(QPoint(0, 0))
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        group = QParallelAnimationGroup(self)
        group.addAnimation(fade)
        group.addAnimation(slide)
        group.finished.connect(self._finish)
        self._group = group
        group.start()


# ─────────────────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────────────────

class NavButton(QPushButton):
    def __init__(self, glyph: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("navBtn")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self.group = None
        self._hover = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 12, 0)
        lay.setSpacing(12)
        self.icon = QLabel(glyph)
        self.icon.setFixedWidth(22)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setFont(symbol_font(13))
        self.label = QLabel(text)
        for w in (self.icon, self.label):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(self.icon)
        lay.addWidget(self.label, 1)
        self.toggled.connect(lambda _: self._restyle())
        self._restyle()

    def enterEvent(self, e):
        self._hover = True
        self._restyle()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._restyle()
        super().leaveEvent(e)

    def _restyle(self):
        if self.isChecked():
            ic, tc, fw = T.ACCENT, T.TEXT, 700
        elif self._hover:
            ic, tc, fw = T.TEXT, T.TEXT, 600
        else:
            ic, tc, fw = T.MUTED, T.MUTED, 600
        self.icon.setStyleSheet(f"color:{ic};")
        self.label.setStyleSheet(f"color:{tc}; font-weight:{fw}; font-size:10pt;")


class NavGroup(QWidget):
    toggled = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.expanded = True
        self._anim = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 10, 0, 0)
        v.setSpacing(2)

        self.header = QPushButton()
        self.header.setObjectName("groupHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setFixedHeight(30)
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(16, 0, 14, 0)
        self.title = QLabel(title)
        self.title.setStyleSheet(f"color:{T.MUTED}; font-size:8pt; font-weight:800; letter-spacing:1px;")
        self.chevron = QLabel("⌃")
        self.chevron.setFont(symbol_font(10, True))
        self.chevron.setStyleSheet(f"color:{T.MUTED};")
        for w in (self.title, self.chevron):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        hl.addWidget(self.title)
        hl.addStretch()
        hl.addWidget(self.chevron)
        v.addWidget(self.header)

        self.body = QWidget()
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(0, 0, 0, 0)
        self.body_l.setSpacing(2)
        v.addWidget(self.body)
        self.header.clicked.connect(self.toggle)

    def toggle(self):
        self.expanded = not self.expanded
        self.chevron.setText("⌃" if self.expanded else "⌄")
        start = self.body.height()
        end = self.body.sizeHint().height() if self.expanded else 0
        if self._anim:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(260)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def step(val):
            self.body.setMaximumHeight(int(val))
            self.toggled.emit()

        def done():
            if self.expanded:
                self.body.setMaximumHeight(16777215)
            self.toggled.emit()

        anim.valueChanged.connect(step)
        anim.finished.connect(done)
        self._anim = anim
        anim.start()


class Sidebar(QFrame):
    selected = pyqtSignal(int)

    def __init__(self, logo_path: str = "", version: str = "v1.0.0", parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(244)
        self.buttons: dict[int, NavButton] = {}
        self._current = None
        self._anim = None

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        brand = QWidget()
        brand.setFixedHeight(72)
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(20, 0, 16, 0)
        bl.setSpacing(12)
        logo = QLabel()
        pix = QPixmap(logo_path)
        if not pix.isNull():
            logo.setPixmap(pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        bl.addWidget(logo)
        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        name = QLabel("StreamStudio")
        name.setStyleSheet("font-size:13pt; font-weight:800;")
        sub = QLabel("Studio para Twitch")
        sub.setStyleSheet(f"font-size:8pt; color:{T.MUTED}; font-weight:600;")
        name_col.addWidget(name)
        name_col.addWidget(sub)
        bl.addLayout(name_col)
        bl.addStretch()
        v.addWidget(brand)

        self.nav = QWidget()
        self.nl = QVBoxLayout(self.nav)
        self.nl.setContentsMargins(12, 6, 12, 6)
        self.nl.setSpacing(2)
        self.pill = QFrame(self.nav)
        self.pill.setObjectName("navPill")
        self.bar = QFrame(self.nav)
        self.bar.setObjectName("navBar")
        v.addWidget(self.nav, 1)

        footer = QLabel(f"Media Hub • {version}")
        footer.setStyleSheet(f"color:{T.MUTED}; font-size:8pt; padding:14px 20px;")
        v.addWidget(footer)

    def add_group(self, title: str) -> NavGroup:
        g = NavGroup(title)
        g.toggled.connect(self._sync)
        self.nl.addWidget(g)
        return g

    def add_item(self, index: int, glyph: str, text: str, group: NavGroup | None = None):
        btn = NavButton(glyph, text)
        btn.group = group
        (group.body_l if group else self.nl).addWidget(btn)
        btn.clicked.connect(lambda _=False, i=index: self.select(i))
        self.buttons[index] = btn

    def finish(self):
        self.nl.addStretch(1)
        self.bar.lower()
        self.pill.lower()

    def select(self, index: int, animated: bool = True, emit: bool = True):
        for i, b in self.buttons.items():
            b.setChecked(i == index)
        self._current = index
        self._move(animated and self.isVisible())
        if emit:
            self.selected.emit(index)

    def _targets(self):
        btn = self.buttons.get(self._current)
        if btn is None:
            return None
        if btn.group is not None and btn.group.body.height() < 6:
            return None
        p = btn.mapTo(self.nav, QPoint(0, 0))
        r = QRect(p.x(), p.y(), btn.width(), btn.height())
        return r, QRect(r.x(), r.y() + 9, 3, r.height() - 18)

    def _move(self, animated: bool):
        t = self._targets()
        if self._anim:
            self._anim.stop()
            self._anim = None
        if t is None:
            self.pill.hide()
            self.bar.hide()
            return
        pill_r, bar_r = t
        first = not self.pill.isVisible()
        self.pill.show()
        self.bar.show()
        if not animated or first:
            self.pill.setGeometry(pill_r)
            self.bar.setGeometry(bar_r)
            return
        group = QParallelAnimationGroup(self)
        for w, r in ((self.pill, pill_r), (self.bar, bar_r)):
            a = QPropertyAnimation(w, b"geometry")
            a.setDuration(380)
            a.setStartValue(w.geometry())
            a.setEndValue(r)
            a.setEasingCurve(QEasingCurve.Type.OutBack if w is self.bar else QEasingCurve.Type.OutCubic)
            group.addAnimation(a)
        self._anim = group
        group.start()

    def _sync(self):
        self._move(False)

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._sync)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._sync)


# ─────────────────────────────────────────────────────────────────────────────
#  Pestañas con subrayado deslizante
# ─────────────────────────────────────────────────────────────────────────────

class TabBar(QWidget):
    changed = pyqtSignal(int)

    def __init__(self, labels: list[str], current: int = 0, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self._current = current
        self._anim = None
        self.buttons: list[QPushButton] = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        for i, text in enumerate(labels):
            b = QPushButton(text)
            b.setObjectName("tabBtn")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, idx=i: self.set_current(idx))
            lay.addWidget(b)
            self.buttons.append(b)
        lay.addStretch()
        self.line = QFrame(self)
        self.line.setStyleSheet(f"background:{T.ACCENT}; border-radius:1px;")
        self._restyle()

    def _restyle(self):
        for i, b in enumerate(self.buttons):
            col = T.ACCENT if i == self._current else T.MUTED
            b.setStyleSheet(f"color:{col}; font-weight:700;")

    def _target(self) -> QRect:
        b = self.buttons[self._current]
        return QRect(b.x() + 12, self.height() - 3, max(10, b.width() - 24), 3)

    def set_current(self, idx: int, emit: bool = True):
        if idx == self._current and self.line.isVisible():
            return
        self._current = idx
        self._restyle()
        if self._anim:
            self._anim.stop()
        a = QPropertyAnimation(self.line, b"geometry", self)
        a.setDuration(320)
        a.setStartValue(self.line.geometry())
        a.setEndValue(self._target())
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim = a
        a.start()
        if emit:
            self.changed.emit(idx)

    def current(self) -> int:
        return self._current

    def _sync(self):
        self.line.setGeometry(self._target())
        self.line.show()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._sync)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._sync)


# ─────────────────────────────────────────────────────────────────────────────
#  Tarjeta de métrica con conteo animado y elevación al pasar el cursor
# ─────────────────────────────────────────────────────────────────────────────

class StatCard(QFrame):
    def __init__(self, title: str, glyph: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(124)
        self._value = 0
        self._shown = 0
        self._suffix = ""
        self._anim = None

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(self._shadow)
        self._shadow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_anim.setDuration(220)

        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(2)
        self.icon = QLabel(glyph)
        self.icon.setFont(symbol_font(18, True))
        self.icon.setStyleSheet(f"color:{color};")
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_lbl = QLabel("0")
        self.value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_lbl.setStyleSheet("font-size:24pt; font-weight:800;")
        self.caption = QLabel(title)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setStyleSheet(f"color:{T.MUTED}; font-size:9pt; font-weight:600;")
        v.addWidget(self.icon)
        v.addWidget(self.value_lbl)
        v.addWidget(self.caption)

    def set_value(self, n: int, suffix: str = ""):
        self._suffix = suffix
        n = int(n)
        if n == self._value:
            return
        if self._anim:
            self._anim.stop()
        a = QVariantAnimation(self)
        a.setStartValue(self._shown)
        a.setEndValue(n)
        a.setDuration(750)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.valueChanged.connect(self._tick)
        a.finished.connect(lambda: self._tick(n))
        self._anim = a
        self._value = n
        a.start()

    def _tick(self, v):
        self._shown = int(v)
        self.value_lbl.setText(f"{self._shown:,}{self._suffix}")

    def _hover(self, blur: float):
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(blur)
        self._shadow_anim.start()

    def enterEvent(self, e):
        self._hover(30)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover(8)
        super().leaveEvent(e)


# ─────────────────────────────────────────────────────────────────────────────
#  Gráfico de actividad animado (fondo punteado como StreamElements)
# ─────────────────────────────────────────────────────────────────────────────

class ActivityChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(280)
        self.setMouseTracking(True)
        self._values: list[float] = []
        self._labels: list[str] = []
        self._color = QColor(T.ACCENT)
        self._progress = 1.0
        self._hover = -1
        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(800)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_progress(self):
        return self._progress

    def _set_progress(self, v):
        self._progress = v
        self.update()

    progress = pyqtProperty(float, _get_progress, _set_progress)

    def set_data(self, values, labels, color: str):
        self._values = list(values)
        self._labels = list(labels)
        self._color = QColor(color)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _geometry(self):
        left, right, top, bottom = 44, 14, 18, 30
        return QRectF(left, top, self.width() - left - right, self.height() - top - bottom)

    def mouseMoveEvent(self, e):
        area = self._geometry()
        n = max(1, len(self._values))
        idx = int((e.position().x() - area.left()) / (area.width() / n))
        idx = idx if 0 <= idx < len(self._values) else -1
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self._geometry()

        # Fondo punteado
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2F3350"))
        for x in range(int(area.left()), int(area.right()), 14):
            for y in range(int(area.top()), int(area.bottom()), 14):
                p.drawEllipse(QPointF(x, y), 1.0, 1.0)

        vmax = max(self._values, default=0)
        ymax = max(4, int(math.ceil(vmax / 4.0)) * 4) if vmax else 4
        font = QFont("Segoe UI", 8)
        p.setFont(font)
        for i in range(5):
            y = area.bottom() - area.height() * i / 4
            p.setPen(QPen(QColor("#2B2F47"), 1))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(T.MUTED))
            p.drawText(QRectF(0, y - 9, area.left() - 8, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{int(ymax * i / 4)}")

        n = len(self._values)
        if n == 0:
            return
        slot = area.width() / n
        bw = min(34.0, slot * 0.52)
        for i, val in enumerate(self._values):
            h = (val / ymax) * area.height() * self._progress
            x = area.left() + slot * i + (slot - bw) / 2
            rect = QRectF(x, area.bottom() - h, bw, h)
            hovered = i == self._hover
            if h > 0.5:
                grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                top_c = self._color.lighter(130 if hovered else 112)
                grad.setColorAt(0, top_c)
                grad.setColorAt(1, blend(self._color, QColor(T.CARD), 0.55))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(grad))
                path = QPainterPath()
                path.addRoundedRect(rect, 5, 5)
                p.drawPath(path)
            else:
                p.setPen(QPen(self._color, 2))
                p.drawLine(QPointF(x, area.bottom() - 1), QPointF(x + bw, area.bottom() - 1))
            p.setPen(QColor(T.TEXT if hovered else T.MUTED))
            p.drawText(QRectF(area.left() + slot * i - 6, area.bottom() + 6, slot + 12, 18),
                       Qt.AlignmentFlag.AlignCenter, self._labels[i])
            if hovered:
                txt = f"{int(val)}"
                bub = QRectF(x + bw / 2 - 20, rect.top() - 28, 40, 22)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#0D1021"))
                p.drawRoundedRect(bub, 6, 6)
                p.setPen(QColor(T.TEXT))
                p.drawText(bub, Qt.AlignmentFlag.AlignCenter, txt)

        if all(v == 0 for v in self._values):
            p.setPen(QColor(T.MUTED))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "Sin actividad registrada en este periodo")


# ─────────────────────────────────────────────────────────────────────────────
#  Switch animado
# ─────────────────────────────────────────────────────────────────────────────

class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get(self):
        return self._offset

    def _set(self, v):
        self._offset = v
        self.update()

    offset = pyqtProperty(float, _get, _set)

    def _animate(self, on: bool):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_checked_silent(self, on: bool):
        self.blockSignals(True)
        self.setChecked(on)
        self._offset = 1.0 if on else 0.0
        self.blockSignals(False)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(blend(QColor("#3A3F58"), QColor(T.ACCENT), self._offset))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 13, 13)
        x = 3 + (self.width() - 26) * self._offset
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, 3, 20, 20))


# ─────────────────────────────────────────────────────────────────────────────
#  Tile seleccionable (temas / personalidades de voz)
# ─────────────────────────────────────────────────────────────────────────────

class SelectTile(QFrame):
    clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str, accent: str, swatch: bool = False, parent=None):
        super().__init__(parent)
        self.accent = QColor(accent)
        self._swatch = swatch
        self._glow = 0.0
        self._hover = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(86)
        self._anim = QPropertyAnimation(self, b"glow", self)
        self._anim.setDuration(260)
        self._hanim = QPropertyAnimation(self, b"hover", self)
        self._hanim.setDuration(180)

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14 if not swatch else 44, 16, 12)
        v.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet("font-weight:800; font-size:10pt;")
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{T.MUTED}; font-size:8.5pt;")
        v.addWidget(t)
        v.addWidget(s)
        v.addStretch()

    def _g(self):
        return self._glow

    def _sg(self, v):
        self._glow = v
        self.update()

    glow = pyqtProperty(float, _g, _sg)

    def _h(self):
        return self._hover

    def _sh(self, v):
        self._hover = v
        self.update()

    hover = pyqtProperty(float, _h, _sh)

    def set_selected(self, on: bool, animate: bool = True):
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._glow)
            self._anim.setEndValue(1.0 if on else 0.0)
            self._anim.start()
        else:
            self._glow = 1.0 if on else 0.0
            self.update()

    def enterEvent(self, e):
        self._hanim.stop()
        self._hanim.setStartValue(self._hover)
        self._hanim.setEndValue(1.0)
        self._hanim.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hanim.stop()
        self._hanim.setStartValue(self._hover)
        self._hanim.setEndValue(0.0)
        self._hanim.start()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        bg = blend(QColor(T.CARD_ALT), QColor("#2A2E42"), self._hover)
        bg = blend(bg, blend(QColor(T.CARD_ALT), self.accent, 0.16), self._glow)
        border = blend(blend(QColor(T.BORDER), QColor("#4A5073"), self._hover), self.accent, self._glow)
        p.setBrush(bg)
        p.setPen(QPen(border, 2 if self._glow > 0.05 else 1.2))
        p.drawRoundedRect(rect, 12, 12)
        if self._swatch:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.accent)
            p.drawEllipse(QRectF(16, 14, 22, 22))
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawEllipse(QRectF(21, 18, 8, 8))
        if self._glow > 0.02:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self.accent.red(), self.accent.green(), self.accent.blue(), int(255 * self._glow)))
            p.drawEllipse(QRectF(self.width() - 30, 12, 16, 16))
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(QPointF(self.width() - 26, 20), QPointF(self.width() - 23, 23))
            p.drawLine(QPointF(self.width() - 23, 23), QPointF(self.width() - 18, 17))


# ─────────────────────────────────────────────────────────────────────────────
#  Mascota de estado (como el bot de StreamElements) y avatar
# ─────────────────────────────────────────────────────────────────────────────

class Mascot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(92, 92)
        self._ok = False
        self._t = 0.0
        a = QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(1800)
        a.setLoopCount(-1)
        a.valueChanged.connect(self._tick)
        a.start()
        self._anim = a

    def _tick(self, v):
        self._t = float(v)
        self.update()

    def set_connected(self, ok: bool):
        self._ok = ok
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        face = QColor(T.GREEN if self._ok else T.RED)
        if self._ok:
            r = 34 + self._t * 12
            ring = QColor(face.red(), face.green(), face.blue(), int(130 * (1 - self._t)))
            p.setPen(QPen(ring, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(face)
        p.drawEllipse(c, 34, 34)
        p.setBrush(QColor("white"))
        for dx in (-12, 12):
            p.drawEllipse(QPointF(c.x() + dx, c.y() - 7), 7, 8)
        p.setBrush(QColor("#1F2937"))
        for dx in (-12, 12):
            p.drawEllipse(QPointF(c.x() + dx, c.y() - 6), 3.4, 3.6)
        p.setPen(QPen(QColor("#1F2937"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self._ok:
            p.drawArc(QRectF(c.x() - 13, c.y() + 2, 26, 18), 200 * 16, 140 * 16)
        else:
            p.drawArc(QRectF(c.x() - 11, c.y() + 12, 22, 14), 20 * 16, 140 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T.CYAN))
            p.drawEllipse(QPointF(c.x() - 12, c.y() + 6 + self._t * 12), 3, 4)


class Avatar(QWidget):
    def __init__(self, size: int = 40, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._text = "S"
        self._color = QColor(T.PURPLE)

    def set_name(self, name: str):
        self._text = (name[:1] or "S").upper()
        self._color = QColor.fromHsv((sum(map(ord, name or "S")) * 37) % 360, 150, 235)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        p.setPen(QColor("white"))
        f = QFont("Segoe UI", int(self.width() * 0.34))
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


# ─────────────────────────────────────────────────────────────────────────────
#  Vista previa animada de la alerta de OBS
# ─────────────────────────────────────────────────────────────────────────────

class AlertPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(210)
        self._accent = QColor(T.PURPLE)
        self._t = 0.0
        a = QVariantAnimation(self)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setDuration(3200)
        a.setLoopCount(-1)
        a.valueChanged.connect(self._tick)
        a.start()
        self._anim = a

    def _tick(self, v):
        self._t = float(v)
        self.update()

    def set_accent(self, hex_color: str):
        self._accent = QColor(hex_color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QLinearGradient(0, 0, self.width(), self.height())
        bg.setColorAt(0, QColor("#1E1B4B"))
        bg.setColorAt(1, QColor("#090D16"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(self.rect(), 12, 12)
        p.setBrush(QColor(255, 255, 255, 14))
        for x in range(14, self.width(), 18):
            for y in range(14, self.height(), 18):
                p.drawEllipse(QPointF(x, y), 1, 1)

        w = min(380, self.width() - 40)
        h = 118
        bob = math.sin(self._t * 2 * math.pi) * 5
        card = QRectF((self.width() - w) / 2, (self.height() - h) / 2 + bob, w, h)
        for i in range(4, 0, -1):
            glow = QColor(self._accent.red(), self._accent.green(), self._accent.blue(), 16)
            p.setBrush(glow)
            p.drawRoundedRect(card.adjusted(-i * 3, -i * 3, i * 3, i * 3), 18 + i * 2, 18 + i * 2)
        p.setBrush(QColor(15, 23, 42, 240))
        p.setPen(QPen(self._accent, 2))
        p.drawRoundedRect(card, 16, 16)

        badge = QRectF(card.center().x() - 90, card.top() + 12, 180, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._accent)
        p.drawRoundedRect(badge, 10, 10)
        p.setPen(QColor("white"))
        f = QFont("Segoe UI", 7)
        f.setBold(True)
        p.setFont(f)
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, "NUEVO SUSCRIPTOR • TIER 1")

        f = QFont("Segoe UI", 15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(card.left(), card.top() + 36, card.width(), 30),
                   Qt.AlignmentFlag.AlignCenter, "NekoValkyrie")
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QColor("#CBD5E1"))
        p.drawText(QRectF(card.left(), card.top() + 66, card.width(), 20),
                   Qt.AlignmentFlag.AlignCenter, "¡Gracias por apoyar el canal!")

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._accent)
        for i in range(5):
            bh = 5 + abs(math.sin(self._t * 2 * math.pi + i * 0.9)) * 13
            bx = card.center().x() - 32 + i * 14
            p.drawRoundedRect(QRectF(bx, card.bottom() - 12 - bh, 6, bh), 3, 3)


# ─────────────────────────────────────────────────────────────────────────────
#  Notificaciones (toasts) con desplazamiento
# ─────────────────────────────────────────────────────────────────────────────

def show_toast(window: QWidget, text: str, color: str = T.GREEN):
    toasts = getattr(window, "_toasts", None)
    if toasts is None:
        toasts = []
        window._toasts = toasts

    box = QFrame(window)
    box.setStyleSheet(
        f"background:{T.CARD}; border:1px solid {color}; border-left:4px solid {color}; border-radius:10px;"
    )
    lay = QHBoxLayout(box)
    lay.setContentsMargins(16, 12, 18, 12)
    lbl = QLabel(text)
    lbl.setStyleSheet("background:transparent; border:none; font-weight:600;")
    lay.addWidget(lbl)
    box.adjustSize()
    box.show()
    box.raise_()

    margin = 22
    idx = len(toasts)
    toasts.append(box)
    y = window.height() - margin - (box.height() + 10) * (idx + 1) + 10
    x_end = window.width() - box.width() - margin
    box.move(window.width() + 10, y)

    eff = QGraphicsOpacityEffect(box)
    box.setGraphicsEffect(eff)

    slide_in = QPropertyAnimation(box, b"pos", box)
    slide_in.setDuration(420)
    slide_in.setStartValue(QPoint(window.width() + 10, y))
    slide_in.setEndValue(QPoint(x_end, y))
    slide_in.setEasingCurve(QEasingCurve.Type.OutBack)
    fade_in = QPropertyAnimation(eff, b"opacity", box)
    fade_in.setDuration(300)
    fade_in.setStartValue(0.0)
    fade_in.setEndValue(1.0)
    grp = QParallelAnimationGroup(box)
    grp.addAnimation(slide_in)
    grp.addAnimation(fade_in)
    grp.start()

    def leave():
        out = QPropertyAnimation(box, b"pos", box)
        out.setDuration(360)
        out.setStartValue(box.pos())
        out.setEndValue(QPoint(window.width() + 10, box.y()))
        out.setEasingCurve(QEasingCurve.Type.InCubic)
        fade = QPropertyAnimation(eff, b"opacity", box)
        fade.setDuration(360)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        g2 = QParallelAnimationGroup(box)
        g2.addAnimation(out)
        g2.addAnimation(fade)

        def cleanup():
            if box in toasts:
                toasts.remove(box)
            box.deleteLater()

        g2.finished.connect(cleanup)
        g2.start()

    QTimer.singleShot(2800, leave)
