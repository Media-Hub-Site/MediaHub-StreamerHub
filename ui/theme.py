"""
ui/theme.py
───────────
Paleta de colores y hoja de estilos global de StreamStudio (dashboard oscuro profesional).
"""

BG = "#0D1021"
SIDEBAR = "#161929"
TOPBAR = "#121526"
CARD = "#232637"
CARD_ALT = "#1B1E2E"
BORDER = "#2E3248"
TEXT = "#F2F4FA"
MUTED = "#8D93AB"
ACCENT = "#5B7FFF"
PURPLE = "#9146FF"
GREEN = "#34D399"
RED = "#F87171"
YELLOW = "#FBBF24"
PINK = "#FB7185"
CYAN = "#38BDF8"

SYMBOL_FONT = "Segoe UI Symbol"

THEME_TILES = {
    "twitch_purple": ("Twitch Purple", "#9146FF"),
    "cyber_cyan": ("Cyber Cyan", "#06B6D4"),
    "emerald_neon": ("Emerald Matrix", "#10B981"),
    "crimson_fire": ("Crimson Boss", "#EF4444"),
}

EVENT_STYLE = {
    "follow": ("♥", PINK, "Seguidor"),
    "sub": ("★", ACCENT, "Suscripción"),
    "bits": ("◆", YELLOW, "Bits"),
    "raid": ("➤", RED, "Raid"),
    "channel_points": ("♪", GREEN, "Puntos IA"),
}


def global_qss() -> str:
    return f"""
    * {{ font-family: "Segoe UI", system-ui, sans-serif; }}
    QWidget {{ color: {TEXT}; font-size: 10pt; }}
    QMainWindow, #root {{ background: {BG}; }}
    QLabel {{ background: transparent; }}
    QStackedWidget {{ background: transparent; }}

    #sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
    #topbar {{ background: {TOPBAR}; border-bottom: 1px solid {BORDER}; }}
    #card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
    #card:hover {{ border: 1px solid #424869; }}
    #flatCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
    #banner {{ background: {CARD_ALT}; border: 1px solid {BORDER}; border-radius: 10px; }}
    #row {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
    #row:hover {{ background: #2A2E42; border: 1px solid #424869; }}
    #navPill {{ background: rgba(91,127,255,0.14); border-radius: 10px; }}
    #navBar {{ background: {ACCENT}; border-radius: 1px; }}
    #navBtn {{ background: transparent; border: none; border-radius: 10px; text-align: left; }}
    #navBtn:hover {{ background: rgba(255,255,255,0.04); }}
    #groupHeader {{ background: transparent; border: none; text-align: left; }}
    #tabBtn {{ background: transparent; border: none; color: {MUTED}; font-weight: 600; padding: 0 14px; }}
    #tabBtn:hover {{ color: {TEXT}; }}

    QPushButton#btnPrimary {{
        background: {ACCENT}; color: white; font-weight: 700; border: none;
        border-radius: 8px; padding: 9px 18px;
    }}
    QPushButton#btnPrimary:hover {{ background: #738FFF; }}
    QPushButton#btnPrimary:pressed {{ background: #4A69DB; }}
    QPushButton#btnPurple {{
        background: {PURPLE}; color: white; font-weight: 700; border: none;
        border-radius: 8px; padding: 9px 18px;
    }}
    QPushButton#btnPurple:hover {{ background: #A463FF; }}
    QPushButton#btnWhite {{
        background: #F3F4F6; color: #1F2937; font-weight: 700; border: none;
        border-radius: 8px; padding: 9px 18px;
    }}
    QPushButton#btnWhite:hover {{ background: #FFFFFF; }}
    QPushButton#btnGhost {{
        background: transparent; color: {TEXT}; font-weight: 600;
        border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 16px;
    }}
    QPushButton#btnGhost:hover {{ background: rgba(255,255,255,0.06); border-color: #4A5073; }}
    QPushButton#btnDanger {{
        background: rgba(248,113,113,0.14); color: {RED}; font-weight: 700;
        border: 1px solid rgba(248,113,113,0.45); border-radius: 8px; padding: 8px 16px;
    }}
    QPushButton#btnDanger:hover {{ background: rgba(248,113,113,0.26); }}
    QPushButton#btnSuccess {{
        background: rgba(52,211,153,0.14); color: {GREEN}; font-weight: 700;
        border: 1px solid rgba(52,211,153,0.45); border-radius: 8px; padding: 8px 16px;
    }}
    QPushButton#btnSuccess:hover {{ background: rgba(52,211,153,0.26); }}

    QLineEdit, QComboBox, QSpinBox {{
        background: {CARD_ALT}; color: {TEXT}; border: 1px solid {BORDER};
        border-radius: 8px; padding: 7px 10px; selection-background-color: {ACCENT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
    QLineEdit[readOnly="true"] {{ color: {CYAN}; font-family: Consolas, monospace; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {CARD}; color: {TEXT}; border: 1px solid {BORDER};
        selection-background-color: {ACCENT}; outline: none;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #3A3F5A; border-radius: 4px; min-height: 36px; }}
    QScrollBar::handle:vertical:hover {{ background: #4C5273; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ height: 0; }}

    QSlider::groove:horizontal {{ background: #2B2F45; height: 6px; border-radius: 3px; }}
    QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
    QSlider::handle:horizontal {{
        background: white; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
    }}

    QTableWidget {{
        background: {CARD_ALT}; alternate-background-color: #20243A; color: {TEXT};
        border: 1px solid {BORDER}; border-radius: 10px; gridline-color: transparent;
    }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QHeaderView::section {{
        background: {CARD}; color: {MUTED}; font-weight: 700; padding: 8px; border: none;
    }}
    QToolTip {{
        background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; padding: 5px 8px;
    }}
    """
