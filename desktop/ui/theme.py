# -*- coding: utf-8 -*-
"""E 和风主题：浅色 / 深色 / 跟随系统。只产出配色和 QSS，不碰业务。"""
import os
import subprocess
import sys

LIGHT = dict(
    name='light', bg='#f7f3ea', card='#fffdf8', fg='#2a2a26', muted='#8a8474',
    accent='#2f5d50', accent_fg='#ffffff', ghost='#efe8d9', ghost_hover='#e6dcc8',
    border='#e0d7c4', head='#f2ead9', warn='#f8e6df', ok='#e6efe7',
    sel='#2f5d50', sel_fg='#ffffff', dim_bg='#f2ead9', sel_soft='#e2ece4',
    bad='#b3372c', good='#2c6b3f', tab='#efe8d9', tab_hover='#e9e0cd',
)
DARK = dict(
    name='dark', bg='#1c1a17', card='#24211c', fg='#ece5d8', muted='#9a9284',
    accent='#7fb69f', accent_fg='#10201a', ghost='#2e2a24', ghost_hover='#3a352c',
    border='#3a352c', head='#26221d', warn='#3a2526', ok='#22302a',
    sel='#7fb69f', sel_fg='#10201a', dim_bg='#26221d', sel_soft='#2c3a33',
    bad='#e87b6f', good='#86c79b', tab='#221f1a', tab_hover='#2a2620',
)


def close_icons(dst_dir, p):
    """画两个 16x16 的 ×（普通/悬停），给 QTabBar 的关闭按钮用。"""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
    try:
        os.makedirs(dst_dir, exist_ok=True)
    except Exception:
        import tempfile
        dst_dir = os.path.join(tempfile.gettempdir(), 'mahjong_ui_icons')
        os.makedirs(dst_dir, exist_ok=True)
    out = {}
    for name, color, alpha, bg in (('close', p['fg'], 150, None),
                                   ('close_hover', p['fg'], 255, p['ghost_hover'])):
        pm = QPixmap(24, 24)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        if bg:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(bg))
            painter.drawRoundedRect(0, 0, 24, 24, 4, 4)
        pen = QPen(QColor(color))
        c = QColor(color)
        c.setAlpha(alpha)
        pen = QPen(c)
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(7.5, 7.5), QPointF(16.5, 16.5))
        painter.drawLine(QPointF(16.5, 7.5), QPointF(7.5, 16.5))
        painter.end()
        path = os.path.join(dst_dir, name + '.png')
        pm.save(path)
        out[name] = path.replace('\\', '/')
    return out


def close_pixmap(p, px=14, alpha=170, hover=False):
    """内存里画一个 ×（不落文件，避免中文路径导致 QSS 加载失败）。"""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    c = QColor(p['fg'])
    c.setAlpha(255 if hover else alpha)
    pen = QPen(c)
    pen.setWidthF(max(1.6, px / 7.0))
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    a, b = px * 0.28, px * 0.72
    painter.drawLine(QPointF(a, a), QPointF(b, b))
    painter.drawLine(QPointF(b, a), QPointF(a, b))
    painter.end()
    return pm


def preferred_font():
    from PySide6.QtGui import QFontDatabase
    fams = set(QFontDatabase.families())
    if sys.platform == 'darwin':
        for n in ('PingFang SC', 'Hiragino Sans GB', 'Heiti SC', 'STHeiti'):
            if n in fams:
                return n, 13
    for n in ('Microsoft YaHei UI', 'Microsoft YaHei', 'Noto Sans CJK SC', 'SimHei'):
        if n in fams:
            return n, 10
    return '', 10


def system_is_dark():
    """跟随系统：Windows 读注册表，macOS 读 defaults，其他按浅色。"""
    try:
        if sys.platform == 'win32':
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as k:
                return winreg.QueryValueEx(k, 'AppsUseLightTheme')[0] == 0
        if sys.platform == 'darwin':
            out = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                                 capture_output=True, text=True, timeout=3)
            return 'Dark' in out.stdout
    except Exception:
        pass
    return False


def resolve(mode):
    if mode == 'dark':
        return DARK
    if mode == 'light':
        return LIGHT
    return DARK if system_is_dark() else LIGHT


def qss(p, icons=None, font=None):
    return f"""
QWidget {{ background: {p['bg']}; color: {p['fg']};
    {('font-family: \"' + font[0] + '\"; font-size: ' + str(font[1]) + 'pt;') if font else ''} }}
QMainWindow, QDialog {{ background: {p['bg']}; }}

/* 标签栏：Chrome 那种「选中页与内容连成一片、其余退到后面」的层级 */
QTabWidget::pane {{
    border: none; background: transparent; top: 3px;
}}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: {p['tab']}; color: {p['muted']};
    padding: 9px 5px 9px 14px; margin: 5px 3px 0px 0px;
    border: 1px solid transparent; border-bottom: 2px solid transparent;
    border-top-left-radius: 9px; border-top-right-radius: 9px;
    min-width: 70px;
}}
QTabBar::tab:hover {{ background: {p['tab_hover']}; color: {p['fg']}; }}
QTabBar::tab:selected {{
    background: {p['card']}; color: {p['fg']};
    border: 1px solid {p['border']}; border-bottom: 2px solid {p['accent']};
}}
QTabBar::close-button {{ width: 0px; height: 0px; }}
QToolButton#tabclose {{ background: transparent; border: none; padding: 0px; }}
QToolButton#tabclose:hover {{ background: {p['border']}; border-radius: 4px; }}

QFrame#card {{ background: {p['card']}; border: 1px solid {p['border']}; border-radius: 10px; }}
QFrame#hline {{ background: {p['border']}; max-height: 1px; }}

QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 19pt; font-weight: 700; }}
QLabel#muted {{ color: {p['muted']}; }}
QLabel#sep {{ color: {p['border']}; }}

QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {p['card']}; color: {p['fg']}; border: 1px solid {p['border']};
    border-radius: 7px; padding: 6px 9px; selection-background-color: {p['accent']};
    selection-color: {p['accent_fg']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {p['accent']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px; height: 0px; border: none; background: transparent;
}}

QPushButton {{
    background: {p['ghost']}; color: {p['fg']}; border: 1px solid {p['border']};
    border-radius: 7px; padding: 8px 15px;
}}
QPushButton:hover {{ background: {p['ghost_hover']}; }}
QPushButton:pressed {{ background: {p['border']}; }}
QPushButton:focus {{ border: 1px solid {p['accent']}; }}
QPushButton:disabled {{ color: {p['muted']}; }}
QPushButton#primary {{ background: {p['accent']}; color: {p['accent_fg']}; border: none; }}
QPushButton#primary:hover {{ background: {p['accent']}; }}
QPushButton#primary:disabled {{ background: {p['ghost']}; color: {p['muted']}; }}
QPushButton#quiet {{
    background: transparent; border: 1px solid transparent; color: {p['muted']};
    padding: 4px 8px;
}}
QPushButton#quiet:hover {{ background: {p['ghost']}; color: {p['fg']}; }}

QToolButton {{
    background: transparent; border: 1px solid transparent; border-radius: 7px;
    padding: 6px 8px; color: {p['muted']};
}}
QToolButton:hover {{ background: {p['ghost']}; color: {p['fg']}; }}
QToolButton::menu-indicator {{ image: none; width: 0px; }}

QTableWidget {{
    background: {p['card']}; alternate-background-color: {p['card']};
    gridline-color: {p['border']}; border: none;
    selection-background-color: {p['sel_soft']}; selection-color: {p['fg']};
}}
QHeaderView::section {{
    background: {p['head']}; color: {p['muted']}; border: none;
    border-bottom: 1px solid {p['border']}; padding: 7px 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {p['head']}; border: none; }}

QTextBrowser {{ background: {p['card']}; border: none; padding: 6px 10px; }}
QSplitter::handle {{ background: {p['border']}; width: 1px; }}
QFrame#panel {{ background: {p['card']}; border: 1px solid {p['border']};
                border-radius: 10px; }}

QProgressBar {{ background: {p['ghost']}; border: none; border-radius: 3px; height: 6px; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 3px; }}
QStatusBar {{ background: {p['bg']}; color: {p['muted']}; }}
QMenu {{ background: {p['card']}; border: 1px solid {p['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p['sel']}; color: {p['sel_fg']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
""" + (f"""
QTabBar::close-button {{ image: url(\"{icons['close']}\"); }}
QTabBar::close-button:hover {{ image: url(\"{icons['close_hover']}\"); }}
""" if icons else "")


def doc_css(p):
    return f"""
body {{ color: {p['fg']}; font-size: 10pt; }}
.h1 {{ font-size: 14pt; font-weight: 700; }}
.h2 {{ font-size: 10.5pt; font-weight: 700; color: {p['accent']}; margin-top: 10px; }}
.h3 {{ font-weight: 700; color: {p['accent']}; }}
.term {{ font-weight: 700; color: {p['accent']}; }}
.dim {{ color: {p['muted']}; }}
.bad {{ color: {p['bad']}; font-weight: 700; }}
.mortal {{ color: {p['good']}; }}
.good {{ color: {p['good']}; font-weight: 700; }}
table.five {{ border-collapse: collapse; margin: 6px 0; }}
table.five td, table.five th {{ padding: 3px 14px 3px 0; text-align: left; }}
table.five .k {{ color: {p['muted']}; }}
table.five .v {{ font-weight: 700; }}
table.grid {{ border-collapse: collapse; }}
table.grid td, table.grid th {{ border-bottom: 1px solid {p['border']}; padding: 4px 12px 4px 0; }}
"""
