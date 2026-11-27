# -*- coding: utf-8 -*-
"""麻将记录 · Qt 版主窗口（多标签：记录 + 多个复盘页）"""
import io
import datetime
import json
import os
import re
import sys
import traceback

# 打包成 --windowed 时 sys.stdout 是 None，print 会炸。
# 直接丢进日志文件，别用 StringIO（那样每行都攒在内存里）
if sys.stdout is None or sys.stderr is None:
    class _LogStream:
        def __init__(self, level):
            self.level, self._buf = level, ''

        def write(self, s):
            self._buf += s
            while '\n' in self._buf:
                line, self._buf = self._buf.split('\n', 1)
                if line.strip():
                    try:
                        import logging
                        logging.getLogger('stdout').log(self.level, line)
                    except Exception:
                        pass

        def flush(self):
            pass

    if sys.stdout is None:
        sys.stdout = _LogStream(20)
    if sys.stderr is None:
        sys.stderr = _LogStream(40)

# 让打包后的 exe 也能正常跑 QtWebEngine：没有这些，内嵌网页会是空白
os.environ.setdefault('QT_OPENGL', 'software')
os.environ.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS',
                      '--no-sandbox --disable-gpu --disable-gpu-compositing')

# 打包后 QtWebEngine 的资源/本地化文件在 _internal/PySide6 下，显式指给它，
# 否则内嵌网页会白屏
_MEIPASS = getattr(sys, '_MEIPASS', None)
if _MEIPASS:
    _res = os.path.join(_MEIPASS, 'PySide6', 'resources')
    if os.path.isdir(_res):
        os.environ.setdefault('QTWEBENGINE_RESOURCES_PATH', _res)
    _loc = os.path.join(_MEIPASS, 'PySide6', 'translations', 'qtwebengine_locales')
    if os.path.isdir(_loc):
        os.environ.setdefault('QTWEBENGINE_LOCALES_PATH', _loc)

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal
from PySide6.QtCore import QSize
from PySide6.QtGui import QActionGroup, QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QCheckBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
                               QTableWidget, QTableWidgetItem, QTabBar, QTabWidget, QTextBrowser,
                               QToolButton, QVBoxLayout, QWidget)

QGuiApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
from PySide6.QtWebEngineCore import QWebEngineProfile  # noqa: E402

import core  # noqa: E402
import store  # noqa: E402
from ui import theme  # noqa: E402
from ui.review import ReviewTab, UA  # noqa: E402

COLS = ['类型', '对局', '顺位', '点数', 'rating', '合计失分', '牌效决策', '防守决策', '压力', '严重', '判定']
NUM_COLS = {2, 3, 4, 5, 6, 7, 8, 9}
METRIC_COLS = {5: '合计失分', 6: '每100次牌效决策', 7: '每100次防守决策',
               8: '压力分数', 9: '严重失误'}
SETTINGS = os.path.join(core.HERE, 'settings.json')


def load_settings():
    try:
        with open(SETTINGS, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(SETTINGS, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class CompactTabBar(QTabBar):
    """Chrome 式：标签多了就一起挤窄，不出现滚动条"""

    MIN_W = 74
    MAX_W = 190

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setElideMode(Qt.ElideRight)
        self.setUsesScrollButtons(True)
        self.setExpanding(False)
        self.setMovable(True)
        self.setDrawBase(False)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        n = max(1, self.count())
        avail = max(self.width(), 320) - 8
        size.setWidth(max(self.MIN_W, min(self.MAX_W, avail // n)))
        size.setHeight(44)
        return size

    def minimumTabSizeHint(self, index):
        size = super().minimumTabSizeHint(index)
        size.setWidth(self.MIN_W)
        return size


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception:
            self.failed.emit(traceback.format_exc())


def find_excel():
    """从注册表找 EXCEL.EXE；找不到就返回 None（退回系统默认程序）。"""
    if os.name != 'nt':
        return None
    try:
        import winreg
        subs = (r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\excel.exe',
                r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\excel.exe')
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in subs:
                try:
                    with winreg.OpenKey(root, sub) as k:
                        p = winreg.QueryValueEx(k, '')[0]
                        if p and os.path.exists(p):
                            return p
                except OSError:
                    continue
    except Exception:
        pass
    return None


def shell_open(path):
    """用系统 shell 打开文件或文件夹。直接起 explorer.exe 在打包环境里会 0xc0000142。"""
    if os.name == 'nt':
        import ctypes
        r = ctypes.windll.shell32.ShellExecuteW(None, 'open', str(path), None, None, 1)
        if r <= 32:
            raise OSError(f'ShellExecute 失败（{r}）')
        return
    import subprocess
    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])


def wrap_html(body, p):
    return (f'<html><head><meta charset="utf-8"><style>{theme.doc_css(p)}</style></head>'
            f'<body>{body}</body></html>')


class DetailDialog(QDialog):
    def __init__(self, parent, title, html):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(900, 760)
        lay = QVBoxLayout(self)
        b = QTextBrowser()
        b.setHtml(html)
        lay.addWidget(b, 1)
        btn = QPushButton('关闭')
        btn.clicked.connect(self.accept)
        lay.addWidget(btn, 0, Qt.AlignRight)


class ConfirmRecordDialog(QDialog):
    """记录前的确认 + 备注（备注不再占主界面）"""

    def __init__(self, parent, ids, links=None):
        super().__init__(parent)
        self.setWindowTitle('记录这一场？' if len(ids) == 1 else f'记录这 {len(ids)} 场？')
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        head = QLabel(f'将记录 {len(ids)} 场' if len(ids) > 1 else f'报告 {ids[0]}')
        head.setObjectName('muted')
        lay.addWidget(head)
        if len(ids) > 1:
            box = QPlainTextEdit()
            box.setReadOnly(True)
            box.setFixedHeight(80)
            box.setPlainText('\n'.join(ids))
            lay.addWidget(box)
        lay.addWidget(QLabel('备注（可空，写进表的「备注」列）'))
        self.ed_note = QLineEdit()
        self.ed_note.setPlaceholderText('例如：深夜、被飞、两家掉线')
        lay.addWidget(self.ed_note)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('确认记录')
        ok.setObjectName('primary')
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def note(self):
        return self.ed_note.text().strip()


class CheckpointDialog(QDialog):
    """自定义检查点：维持线 / 检查点"""

    def __init__(self, parent, lines):
        super().__init__(parent)
        self.setWindowTitle('检查点设置')
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        tip = QLabel('检查点（使用凤卓数据计算得出）。开启后，报告里会多出「维持线 / 检查点」两列：'
                     '超维持线标红、达检查点标绿。不开启则完全不显示。')
        tip.setObjectName('muted')
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.chk = QCheckBox('在报告和列表里显示维持线 / 检查点')
        self.chk.setChecked(bool(core.LINES_ON))
        lay.addWidget(self.chk)
        self.spins = []
        grid = QVBoxLayout()
        head = QHBoxLayout()
        for w, t in ((150, '项目'), (90, '维持线'), (90, '检查点')):
            lb = QLabel(t)
            lb.setObjectName('muted')
            lb.setFixedWidth(w)
            head.addWidget(lb)
        head.addStretch(1)
        grid.addLayout(head)
        for name, keep, goal in lines:
            row = QHBoxLayout()
            lb = QLabel(name)
            lb.setFixedWidth(150)
            sk = QDoubleSpinBox()
            sk.setRange(0, 999)
            sk.setDecimals(2)
            sk.setSingleStep(0.5)
            sk.setValue(float(keep))
            sk.setFixedWidth(90)
            sg = QDoubleSpinBox()
            sg.setRange(0, 999)
            sg.setDecimals(2)
            sg.setSingleStep(0.5)
            sg.setValue(float(goal))
            sg.setFixedWidth(90)
            row.addWidget(lb)
            row.addWidget(sk)
            row.addWidget(sg)
            row.addStretch(1)
            grid.addLayout(row)
            self.spins.append((name, sk, sg))
        lay.addLayout(grid)
        row = QHBoxLayout()
        reset = QPushButton('恢复默认')
        reset.clicked.connect(self.reset)
        row.addWidget(reset)
        row.addStretch(1)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('保存')
        ok.setObjectName('primary')
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def reset(self):
        for (name, sk, sg), (_, keep, goal) in zip(self.spins, core.DEFAULT_LINES):
            sk.setValue(float(keep))
            sg.setValue(float(goal))

    def lines(self):
        return [[n, max(0.0, round(sk.value(), 2)), max(0.0, round(sg.value(), 2))]
                for n, sk, sg in self.spins]

    def enabled(self):
        return self.chk.isChecked()

    def normalized(self):
        out = []
        for n, sk, sg in self.spins:
            keep = max(0.0, round(sk.value(), 2))
            goal = max(0.0, round(sg.value(), 2))
            out.append([n, keep, min(goal, keep)])
        return out


class NumItem(QTableWidgetItem):
    """按数值排序的单元格（不然 9 会排在 10 后面）"""

    def __lt__(self, other):
        a, b = self.text(), other.text()
        try:
            return float(a) < float(b)
        except ValueError:
            return a < b


class DataTab(QWidget):
    """像 Excel 一样看全表：所有列、可排序、可搜索"""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.p = win.p
        self.head = list(core.mr.XLSX_HEAD)
        if '数据' in self.head:
            self.head.remove('数据')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索：日期 / 卓 / 报告 id / 备注…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.load)
        self.count = QLabel('')
        self.count.setObjectName('muted')
        btn_reload = QPushButton('刷新')
        btn_reload.clicked.connect(self.refresh)
        btn_import = QPushButton('导入 Excel')
        btn_import.clicked.connect(self.import_excel)
        btn_export = QPushButton('导出 Excel')
        btn_export.clicked.connect(win.record_tab.export_excel)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.count)
        bar.addWidget(btn_reload)
        bar.addWidget(btn_import)
        bar.addWidget(btn_export)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(self.head))
        self.table.setHorizontalHeaderLabels(self.head)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 130)
        self.table.doubleClicked.connect(self.on_double)
        lay.addWidget(self.table, 1)
        self._rows = []
        self.refresh()
        self.table.sortItems(0, Qt.DescendingOrder)

    def import_excel(self):
        import_path, _ = QFileDialog.getOpenFileName(self, '选择旧的麻将逐场数据.xlsx', core.BASE, 'Excel (*.xlsx)')
        if not import_path:
            return
        try:
            n = store.import_xlsx(import_path)
        except Exception as exc:
            QMessageBox.warning(self, '导入失败', str(exc))
            return
        self.refresh()
        self.win.record_tab.status.setText(f'已从 {os.path.basename(import_path)} 导入 {n} 场，库里现在 {store.count()} 场。')
        QMessageBox.information(self, '导入完成', f'新增 {n} 场，库里共 {store.count()} 场。')

    def refresh(self):
        try:
            self._rows = store.all_rows()
        except Exception:
            self._rows = []
        self.load()

    def load(self, *_):
        kw = self.search.text().strip().lower()
        rows = [r for r in self._rows
                if not kw or kw in ' '.join(str(v) for v in r.values()).lower()]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, h in enumerate(self.head):
                v = r.get(h, '')
                it = NumItem('' if v is None else str(v))
                it.setTextAlignment((Qt.AlignRight if c >= 3 else Qt.AlignCenter) | Qt.AlignVCenter)
                self.table.setItem(i, c, it)
        self.table.setSortingEnabled(True)
        self.count.setText(f'{len(rows)} / {len(self._rows)} 场')
        self.status_tip = len(rows)

    def on_double(self, *_):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        rid_item = self.table.item(r, self.head.index('报告ID'))
        rid = rid_item.text() if rid_item else ''
        if not rid:
            return
        cached = self.win.record_tab.details.get(rid)
        if cached:
            DetailDialog(self, f'{rid} · 详细', wrap_html(core.game_html(cached), self.p)).exec()
            return
        if getattr(self, '_worker', None) is not None and self._worker.isRunning():
            return
        self.win.statusBar().showMessage(f'正在取 {rid} 的报告……')
        self._worker = Worker(lambda: core.compute(rid))
        self._worker.done.connect(lambda g: self._show_detail(rid, g))
        self._worker.failed.connect(lambda tb: QMessageBox.warning(self, '取不到报告', str(tb).strip().splitlines()[-1]))
        self._worker.start()

    def _show_detail(self, rid, g):
        self.win.statusBar().showMessage('')
        self.win.record_tab.details[rid] = g
        DetailDialog(self, f'{rid} · 详细', wrap_html(core.game_html(g), self.p)).exec()


class RecordTab(QWidget):
    """记录 / 查看 / 审计。左列表 + 右详情，邮件式两栏。"""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.p = win.p
        self.details = {}
        self._audit_html = None
        self.worker = None
        self._buttons = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(9)

        # 1) 牌谱框 + 复盘按钮
        link_row = QHBoxLayout()
        link_row.setSpacing(8)
        self.ed_link = QPlainTextEdit()
        self.ed_link.textChanged.connect(self._sync_button)
        self.ed_link.setPlaceholderText('把天凤 / 雀魂牌谱链接粘在这里，一行一张（回车分隔），点右边「复盘」')
        self.ed_link.setFixedHeight(76)
        self.btn_review = QPushButton('复盘')
        self.btn_review.setObjectName('primary')
        self.btn_review.setFixedWidth(96)
        self.btn_review.setMinimumHeight(76)
        self.btn_review.clicked.connect(self.open_review)
        link_row.addWidget(self.ed_link, 1)
        link_row.addWidget(self.btn_review)
        lay.addLayout(link_row)

        # 3) 分级按钮
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_record = QPushButton('记录一场')
        self.btn_record.setObjectName('primary')
        self.btn_record.clicked.connect(self.record)
        self.btn_view = QPushButton('只看数字')
        self.btn_view.setObjectName('primary')
        self.btn_view.clicked.connect(self.view)
        bar.addWidget(self.btn_record)
        bar.addWidget(self.btn_view)
        bar.addSpacing(10)
        for text, slot in (('牌效审计', self.audit), ('检查点设置', self.edit_checkpoints)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
            self._buttons.append(b)
        bar.addSpacing(10)
        for text, slot in (('导出 Excel', self.export_excel),):
            b = QPushButton(text)
            b.setObjectName('quiet')
            b.clicked.connect(slot)
            bar.addWidget(b)
            self._buttons.append(b)
        bar.addStretch(1)
        guide = QPushButton('使用说明')
        guide.setObjectName('quiet')
        guide.clicked.connect(self.guide)
        bar.addWidget(guide)
        lay.addLayout(bar)

        self.pending = []          # [(报告 id, 牌谱链接)]

        # 4) 左列表 + 右详情
        panel = QFrame()
        panel.setObjectName('panel')
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(1, 1, 1, 0)
        pv.setSpacing(0)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(1)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.doubleClicked.connect(self.open_detail)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setStretchLastSection(True)
        for i, w in enumerate((46, 86, 40, 58, 50, 62, 62, 62, 46, 46)):
            self.table.setColumnWidth(i, w)
        lv.addWidget(self.table, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(8, 6, 8, 7)
        self.count_label = QLabel('')
        self.count_label.setObjectName('muted')
        self.btn_clear = QPushButton('清空列表')
        self.btn_clear.setObjectName('quiet')
        self.btn_clear.clicked.connect(self.clear_rows)
        foot.addWidget(self.count_label)
        foot.addStretch(1)
        foot.addWidget(self.btn_clear)
        lv.addLayout(foot)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        rv.addWidget(self.detail, 1)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        pv.addWidget(split, 1)

        lay.addWidget(panel, 1)

        # 5) 状态
        foot = QHBoxLayout()
        db_broken = ''
        try:
            n = store.count(raise_on_error=True)
        except Exception:
            n, db_broken = 0, '数据库读不出来（文件可能损坏）'
        if db_broken:
            self.status = QLabel(f'⚠ {db_broken}：{store.db_path()}　（原文件没动，可以改名备份后重启）')
        elif getattr(core, 'PATH_FALLBACK', ''):
            self.status = QLabel(f'⚠ 程序目录写不进去，数据改存到：{core.BASE}（{n} 场）')
        elif n:
            self.status = QLabel(f'数据库：{store.db_path()}（{n} 场）')
        else:
            self.status = QLabel('数据库是空的：切到「数据」→「导入 Excel」把旧表导进来，或直接复盘记录新的一场。')
        self.status.setObjectName('muted')
        self.bar = QProgressBar()
        self.bar.setFixedWidth(160)
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        foot.addWidget(self.status, 1)
        foot.addWidget(self.bar)
        lay.addLayout(foot)


        self.empty = QLabel('还没有结果\n\n粘牌谱 → 复盘 → 记录', self.table.viewport())
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName('muted')
        self.empty.resize(320, 70)
        self.table.viewport().installEventFilter(self)
        self._place_empty()
        self.show_selected()

    # ---------- 布局细节
    def eventFilter(self, obj, ev):
        if obj is self.table.viewport() and ev.type() == QEvent.Resize:
            self._place_empty()
        return super().eventFilter(obj, ev)

    def _place_empty(self):
        vp = self.table.viewport()
        self.empty.move(max(0, (vp.width() - 320) // 2), max(0, vp.height() // 2 - 40))

    def show_selected(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            self.detail.setHtml(wrap_html(
                '<p class="dim">左边选一场，这里显示重点 5 项和 Q 差最大的 10 手。</p>', self.p))
            return
        data = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        if isinstance(data, tuple) and data and data[0] == 'audit':
            self.detail.setHtml(wrap_html(data[1], self.p))
            return
        g = self.details.get(data) if data else None
        if g:
            self.detail.setHtml(wrap_html(core.game_html(g), self.p))

    # ---------- 数据
    def bare_ids(self):
        """牌谱框里单独粘的 16 位报告 id（不走复盘页时用）"""
        out = []
        for line in re.split(r'[\r\n]+', self.ed_link.toPlainText()):
            line = line.strip()
            if re.fullmatch(r'[0-9a-f]{16}', line):
                out.append(line)
        return out

    def pending_ids(self):
        seen, out = set(), []
        for rid, _ in self.pending + [(x, '') for x in self.bare_ids()]:
            if rid not in seen:
                seen.add(rid)
                out.append(rid)
        return out

    def _on_worker_finished(self):
        self._running = False
        if getattr(self.win, '_close_when_idle', False):
            self.win._close_when_idle = False
            self.win.close()

    def _sync_button(self):
        n = len(self.pending_ids())
        if not (self.worker and self.worker.isRunning()):
            self.btn_record.setText(f'记录 {n} 场' if n > 1 else '记录一场')

    def add_pending(self, rid, link=''):
        if any(rid == r for r, _ in self.pending):
            return
        if len(self.pending) >= 40:
            self.status.setText('待记录已经 40 场了，先记一批再继续。')
            return
        self.pending.append((rid, link))
        n = len(self.pending_ids())
        self.btn_record.setText(f'记录 {n} 场' if n > 1 else '记录一场')
        self.status.setText(f'已取到 {n} 份报告，点「{self.btn_record.text()}」。')

    def links(self):
        text = self.ed_link.toPlainText()
        out = []
        for line in re.split(r'[\r\n]+', text):
            line = line.strip()
            if line and re.search(r'https?://|tenhou|paipu|majsoul', line, re.I):
                out.append(line)
        return out

    def set_busy(self, on, msg=None):
        for b in [self.btn_record, self.btn_view, self.btn_review] + getattr(self, '_buttons', []):
            b.setEnabled(not on)
        self.bar.setRange(0, 0 if on else 1)
        self.bar.setValue(0)
        if msg:
            self.status.setText(msg)

    def _color_for(self, col, text):
        name = METRIC_COLS.get(col)
        if not name:
            if col == 10:
                if text.startswith('超'):
                    return self.p['bad']
                if '在线内' in text or text.startswith('达'):
                    return self.p['good']
            return None
        try:
            v = float(text)
        except ValueError:
            return None
        state = core.line_state(name, v)
        return self.p['bad'] if state == 'bad' else (self.p['good'] if state == 'good' else None)

    def add_row(self, kind, g, label):
        five = [core.fmt5(n, v) for (n, _, _), (v, _) in zip(core.LINES, g['five'])]
        vals = [kind, label, str(g['rank']), str(g['score']), f'{g["rating"]:.1f}'] + five + [core.verdict_short(g['five'])]
        self.table.insertRow(0)
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            it.setTextAlignment((Qt.AlignRight if c in NUM_COLS else Qt.AlignCenter) | Qt.AlignVCenter)
            color = self._color_for(c, v)
            if color:
                if color:
                    it.setForeground(QColor(color))
                else:
                    it.setData(Qt.ForegroundRole, None)
            if c == 0:
                it.setData(Qt.UserRole, g['rid'])
            self.table.setItem(0, c, it)
        self.details[g['rid']] = g
        while len(self.details) > 30:   # 每场都是完整分析结果，留太多会占几百 MB
            self.details.pop(next(iter(self.details)), None)
        self.table.selectRow(0)
        self.empty.hide()
        self.count_label.setText(f'{self.table.rowCount()} 条')
        self.show_selected()

    def clear_rows(self):
        self.table.setRowCount(0)
        self.details.clear()
        self._audit_html = None
        self.count_label.setText('')
        self.detail.clear()
        self.empty.show()

    # ---------- 记录
    def record(self):
        ids = self.pending_ids()
        if not ids:
            QMessageBox.warning(self, '还没有报告', '把牌谱链接粘到上面的框里，点「复盘」；报告出来后会自动收集，再点这里记录。')
            return
        links = dict(self.pending)
        dlg = ConfirmRecordDialog(self, ids, links)
        if dlg.exec() != QDialog.Accepted:
            return
        self.record_ids(ids, dlg.note(), links)

    def _start(self, work, on_done, msg=''):
        if self.worker is not None and self.worker.isRunning():
            self.status.setText('上一个任务还没结束，稍等一下……')
            return False
        if msg:
            self.set_busy(True, msg)
        self.worker = Worker(work)
        self.worker.done.connect(on_done)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._on_worker_finished)
        self._running = True
        self.worker.start()
        return True

    def record_ids(self, ids, note='', links=None):
        links = links or dict(self.pending)

        def work():
            out = []
            for rid in ids:
                try:
                    g, no, existed = core.record_one(rid, links.get(rid, ''), note)
                    out.append((g, no, existed, ''))
                except Exception as exc:
                    out.append((None, None, False, f'{rid}: {exc}'))
            return out

        self._start(work, self._recorded, f'正在记录 {len(ids)} 场……')

    def _recorded(self, results):
        self.set_busy(False)
        added, dup, errs = 0, 0, []
        for item in results:
            g, no, existed = item[0], item[1], item[2]
            err = item[3] if len(item) > 3 else ''
            if not no:
                errs.append(err or (g or {}).get('save_error') or '写入数据库失败')
                continue
            if existed:
                dup += 1
                continue            # 库里已有这场，不要再往表格插一行
            self.add_row('记录', g, f'第 {no} 行')
            added += 1
        done_ids = {it[0]['rid'] for it in results if it[0] and it[1]}
        self.pending = [(r, l) for r, l in self.pending if r not in done_ids]
        self._sync_button()
        try:
            self.win.data_tab.refresh()
        except Exception:
            pass

        parts = []
        if added:
            parts.append(f'已记录 {added} 场')
        if dup:
            parts.append(f'{dup} 场已存在（跳过）')
        if errs:
            parts.append(f'{len(errs)} 场失败')
        detail = ''
        if added:
            bad = [it[0] for it in results if it[0] and it[0].get('save_error')]
            md = next((it[0].get('saved_md') for it in results if it[0] and it[0].get('saved_md')), '')
            if bad:
                detail = f'；{len(bad)} 场存档失败：{bad[0].get("save_error", "")[:60]}'
            elif md:
                detail = f'；存档：{os.path.dirname(md)}'
        self.status.setText('，'.join(parts) + detail if parts else '没有写入任何场次。')
        if errs:
            QMessageBox.critical(self, '部分场次没写进去',
                                 '写入数据库失败：\n' + '\n'.join(errs[:3]))

    def _failed(self, tb):
        self.set_busy(False)
        core.log().error('操作失败:\n%s', tb)
        lines = [x.strip() for x in str(tb).strip().splitlines() if x.strip()]
        QMessageBox.critical(self, '出错了', (lines[-1] if lines else '未知错误')
                                 + f'\n\n详细日志：{os.path.join(core.log_dir(), "app.log")}')
        print(tb)

    def view(self):
        ids = self.pending_ids()
        if not ids:
            QMessageBox.warning(self, '还没有报告', '先把牌谱链接粘上去、点「复盘」。')
            return
        rid = ids[0]
        self._start(lambda: core.compute(rid), self._viewed, '正在取报告、计算……')

    def _viewed(self, g):
        self.set_busy(False)
        self.add_row('查看', g, g['rid'][:8])
        self.status.setText('只看数字，没有写表。')

    # ---------- 复盘
    def open_review(self):
        import time as _t
        now = _t.monotonic()
        if now - getattr(self, '_review_ts', 0) < 0.25:
            return                      # 连点防抖
        self._review_ts = now
        links = self.links()
        # 只粘了一个 16 位报告 id（没有 URL）时，也该能开复盘页——原来 rid 恒为 None，
        # 这个分支永远走不到，用户只会看到「没有可复盘的内容」。
        rid = core.get_rid(self.ed_link.toPlainText()) if not links else None
        if links:
            for i, link in enumerate(links[:6]):
                self.win.open_review(link)
            self.status.setText(f'已开 {min(len(links), 6)} 个复盘标签' +
                                ('（超过 6 条只开前 6 条）' if len(links) > 6 else '') + '，在网页里过验证码提交。')
        elif rid:
            self.win.open_review(rid)
            self.status.setText('已开复盘标签。')
        else:
            QMessageBox.warning(self, '没有可复盘的内容', '先把牌谱链接粘到上面的框里。')

    # ---------- 审计
    def audit(self):
        try:
            games = core.recorded_games()
        except Exception:
            QMessageBox.critical(self, '读不了 Excel', traceback.format_exc()[-800:])
            return
        if not games:
            QMessageBox.information(self, '没有可审计的场次',
                                '数据库里还没有带报告 id 的场次。\n\n'
                                '如果旧数据在 Excel 里：切到「数据」标签，点「导入 Excel」。')
            return
        AuditDialog(self, games, self.run_audit).exec()

    def run_audit(self, picked):
        self.bar.setRange(0, max(1, len(picked)))
        started = self._start(
            lambda: core.audit(picked, progress=lambda i, n, m: self.worker.progress.emit(i, n, m)),
            self._audited, '牌效审计中……')
        if started:
            self.worker.progress.connect(self._progress)

    def _progress(self, i, n, msg):
        self.bar.setRange(0, max(1, n))
        self.bar.setValue(i)
        self.status.setText(msg)

    def _audited(self, res):
        summ, failed = res
        self.set_busy(False)
        top = max(summ['cats'], key=lambda c: c['loss'])
        self.table.insertRow(0)
        vals = ['审计', f'{summ["games"]} 场', '', '', '', f'{summ["le"] / max(1, summ["n"]) * 100:.2f}',
                '', '', '', '', f'最多：{top["k"]}（{top["share_eff"]:.0f}%）']
        html = core.audit_html(summ, failed)
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            it.setTextAlignment((Qt.AlignRight if c in NUM_COLS else Qt.AlignCenter) | Qt.AlignVCenter)
            if c == 0:
                it.setData(Qt.UserRole, ('audit', html))
            self.table.setItem(0, c, it)
        self._audit_html = html
        self.empty.hide()
        self.count_label.setText(f'{self.table.rowCount()} 条')
        self.table.selectRow(0)
        self.show_selected()
        self.status.setText(f'牌效审计完成：{summ["games"]} 场' +
                            (f'，{len(failed)} 场没取到报告' if failed else '') + '。')

    # ---------- 检查点
    def edit_checkpoints(self):
        dlg = CheckpointDialog(self, core.LINES)
        if dlg.exec() == QDialog.Accepted:
            on = dlg.enabled()
            core.set_lines(dlg.normalized(), on)
            self.win.settings['lines'] = dlg.normalized()
            self.win.settings['lines_on'] = on
            save_settings(self.win.settings)
            self.refresh_colors()
            self.show_selected()
            if on:
                self.status.setText('检查点已开启：超维持线标红、达检查点标绿。')
            else:
                self.status.setText('检查点已关闭，报告里不再显示这两列。')

    def refresh_colors(self):
        for r in range(self.table.rowCount()):
            rid = self.table.item(r, 0).data(Qt.UserRole)
            g = self.details.get(rid) if rid else None
            if not g:
                continue
            five = [core.fmt5(n, v) for (n, _, _), (v, _) in zip(core.LINES, g['five'])]
            for c, v in enumerate(five, start=5):
                it = self.table.item(r, c)
                it.setText(v)
                color = self._color_for(c, v)
                if color:
                    it.setForeground(QColor(color))
                else:
                    it.setData(Qt.ForegroundRole, None)
            verdict = core.verdict_short(g['five'])
            it = self.table.item(r, 10)
            it.setText(verdict)
            color = self._color_for(10, verdict)
            if color:
                it.setForeground(QColor(color))
            else:
                it.setData(Qt.ForegroundRole, None)
        self.show_selected()

    # ---------- 文件
    def export_excel(self):
        out_dir = os.path.join(core.BASE, '导出')
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as exc:
            QMessageBox.warning(self, '导出失败', f'建不了导出目录：\n{out_dir}\n\n{exc}')
            return
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M')
        out = os.path.join(out_dir, f'麻将逐场数据_{stamp}.xlsx')
        try:
            n = store.export_xlsx(out, template=core.XLSX if os.path.exists(core.XLSX) else None)
        except Exception as exc:
            QMessageBox.warning(self, '导出失败', f'{out}\n\n{exc}')
            return
        self.status.setText(f'已导出 {n} 场到 {out}')
        try:
            shell_open(out_dir)
        except Exception:
            QMessageBox.information(self, '已导出', out)

    def guide(self):
        DetailDialog(self, f'使用说明（{core.VERSION}）', wrap_html(core.guide_html(), self.p)).exec()

    def open_detail(self, *_):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return
        data = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        if isinstance(data, tuple) and data and data[0] == 'audit':
            DetailDialog(self, '牌效审计 · 详细', wrap_html(data[1], self.p)).exec()
            return
        g = self.details.get(data) if data else None
        if g:
            DetailDialog(self, f'{g["rid"]} · 详细', wrap_html(core.game_html(g), self.p)).exec()


class AuditDialog(QDialog):
    """选场次：勾选状态用文字画，避免深色主题下原生勾选框看不见"""

    def __init__(self, parent, games, on_ok):
        super().__init__(parent)
        self.setWindowTitle('牌效审计：选择场次')
        self.resize(720, 560)
        self.games, self.on_ok = games, on_ok
        self._checked = set()
        self.p = parent.p
        lay = QVBoxLayout(self)
        tip = QLabel('勾选要审计的场次（报告过期且本地没有缓存的会自动跳过）')
        tip.setObjectName('muted')
        lay.addWidget(tip)
        self.table = QTableWidget(len(games), 6)
        self.table.setHorizontalHeaderLabels(['选', '序号', '日期', '卓', '顺位', '报告'])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 44)
        for i, g in enumerate(games):
            chk = QTableWidgetItem('')
            chk.setTextAlignment(Qt.AlignCenter)
            chk.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(i, 0, chk)
            for c, v in enumerate((str(g['no']), g['date'], g['zhuo'], str(g['rank']), g['rid']), 1):
                it = QTableWidgetItem(v)
                it.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, c, it)
        lay.addWidget(self.table, 1)
        self.count_label = QLabel('已选 0 场')
        lay.addWidget(self.count_label)
        row = QHBoxLayout()
        for text, n in (('最近 10 场', 10), ('最近 20 场', 20), ('最近 30 场', 30), ('全选', 0)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, k=n: self.pick_last(k))
            row.addWidget(b)
        b = QPushButton('全不选')
        b.clicked.connect(lambda: self.set_checked([]))
        row.addWidget(b)
        row.addStretch(1)
        cancel = QPushButton('取消')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('开始审计')
        ok.setObjectName('primary')
        ok.clicked.connect(self.accept_pick)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self.table.cellClicked.connect(self._toggle_row)
        self._scrolled = False
        self.pick_last(20)

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._scrolled:
            self._scrolled = True
            self.table.scrollToBottom()

    def _paint(self, i):
        it = self.table.item(i, 0)
        on = i in self._checked
        it.setText('✓' if on else '')
        it.setForeground(QColor(self.p['accent'] if on else 'transparent'))
        for c in range(1, 6):
            cell = self.table.item(i, c)
            if cell is not None:
                cell.setBackground(QColor(self.p['ok'] if on else 'transparent'))

    def _repaint(self):
        for i in range(self.table.rowCount()):
            self._paint(i)
        self.count_label.setText(f'已选 {len(self._checked)} 场')

    def _toggle_row(self, row, col):
        if row < 0:
            return
        self._checked ^= {row}
        self._paint(row)
        self.count_label.setText(f'已选 {len(self._checked)} 场')

    def checked(self):
        return sorted(self._checked)

    def set_checked(self, ids):
        self._checked = set(ids)
        self._repaint()

    def pick_last(self, n):
        ids = list(range(self.table.rowCount()))
        sel = ids if n == 0 else ids[-n:]
        self.set_checked(sel)
        if sel:
            self.table.scrollToItem(self.table.item(sel[-1], 1))

    def accept_pick(self):
        sel = [self.games[i] for i in self.checked()]
        if not sel:
            QMessageBox.warning(self, '没有选择', '请至少勾选一场。')
            return
        self.accept()
        self.on_ok(sel)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        if app is not None:
            fam, size = theme.preferred_font()
            f = app.font()
            if fam:
                f.setFamily(fam)
            f.setPointSize(size)
            app.setFont(f)
        self.log_path = core.setup_logging()
        core.log().info('启动 version=%s frozen=%s base=%s db=%s',
                        core.VERSION, core.FROZEN, core.BASE, store.db_path())
        self.settings = load_settings()
        mode = self.settings.get('theme', 'system')
        if isinstance(mode, int):
            mode = ('system', 'light', 'dark')[mode] if 0 <= mode <= 2 else 'system'
        if mode not in ('system', 'light', 'dark'):
            mode = 'system'
        self.theme_mode = mode
        if self.settings.get('lines'):
            core.set_lines(self.settings['lines'], self.settings.get('lines_on', False))
        self.p = theme.resolve(self.theme_mode)
        self.setWindowTitle(f'麻将记录 {core.VERSION}')
        self.resize(1360, 860)
        self.setMinimumSize(1000, 640)

        self.tabs = QTabWidget()
        self.tabs.setTabBar(CompactTabBar(self.tabs))
        self.tabs.setTabsClosable(False)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(10, 6, 10, 8)
        cl.setSpacing(6)
        top = QHBoxLayout()
        title = QLabel('麻将记录')
        title.setObjectName('h1')
        sub = QLabel(core.VERSION)
        sub.setObjectName('muted')
        top.addWidget(title)
        top.addWidget(sub)
        top.addStretch(1)
        self.btn_theme = QToolButton()
        self.btn_theme.setPopupMode(QToolButton.InstantPopup)
        self.btn_theme.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu = QMenu(self)
        self.theme_group = QActionGroup(self)
        for text, key in (('跟随系统', 'system'), ('浅色', 'light'), ('深色', 'dark')):
            act = menu.addAction(text)
            act.setCheckable(True)
            act.setData(key)
            act.triggered.connect(lambda _=False, k=key: self.set_theme_mode(k))
            self.theme_group.addAction(act)
        self.btn_theme.setMenu(menu)
        top.addWidget(self.btn_theme)
        cl.addLayout(top)
        cl.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self._close_buttons = {}
        self._migrate()
        self.record_tab = RecordTab(self)
        self.tabs.addTab(self.record_tab, '记录')
        self.data_tab = DataTab(self)
        self.tabs.addTab(self.data_tab, '数据')
        self.tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.tabs.tabBar().setTabButton(1, QTabBar.ButtonPosition.RightSide, None)

        self.profile = QWebEngineProfile('mahjong', self)
        self.profile.setPersistentStoragePath(os.path.join(core.HERE, 'webview'))
        self.profile.setCachePath(os.path.join(core.HERE, 'webview', 'cache'))
        self.profile.setHttpUserAgent(UA)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        self.apply_theme()

    def closeEvent(self, ev):
        w = getattr(self.record_tab, 'worker', None)
        if w is not None and w.isRunning():
            ret = QMessageBox.question(
                self, '还在运行', '记录/审计还没结束。\n\n是 = 等它做完再关，否 = 直接关掉（可能丢这一场）。',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ret == QMessageBox.Yes:
                w.wait(60000)
                if w.isRunning():
                    ev.ignore()
                    self.record_tab.status.setText('还在运行，稍等再关。')
                    return
            else:
                self._close_when_idle = True
                w.requestInterruption()
                self.record_tab.status.setText('正在停止……结束后会自动关闭。')
                ev.ignore()
                return
        super().closeEvent(ev)

    _close_when_idle = False

    def _migrate(self):
        """第一次跑：把旧的 Excel 导进库（只导一次）。"""
        try:
            if store.count() == 0 and os.path.exists(core.XLSX):
                n = store.import_xlsx(core.XLSX)
                if n:
                    self.settings['migrated_from'] = core.XLSX
                    save_settings(self.settings)
        except Exception:
            pass

    # ---------- 主题
    def apply_theme(self):
        self.p = theme.resolve(self.theme_mode)
        fam, size = theme.preferred_font()
        app = QApplication.instance()
        f = app.font()
        if fam:
            f.setFamily(fam)
        f.setPointSize(size)
        app.setFont(f)
        icons = theme.close_icons(os.path.join(core.HERE, 'ui_icons'), self.p)
        app.setStyleSheet(theme.qss(self.p, icons, theme.preferred_font()))
        self.record_tab.p = self.p
        self._refresh_close_buttons()
        self.tabs.tabBar().updateGeometry()
        self.tabs.tabBar().update()
        self.btn_theme.setText('外观：' + {'system': '跟随系统', 'light': '浅色', 'dark': '深色'}[self.theme_mode])
        for act in self.theme_group.actions():
            act.setChecked(act.data() == self.theme_mode)

    def set_theme_mode(self, key):
        if isinstance(key, int):
            key = ('system', 'light', 'dark')[key]
        self.theme_mode = key
        self.settings['theme'] = key
        save_settings(self.settings)
        self.apply_theme()
        self.record_tab.refresh_colors()

    # ---------- 标签
    def open_review(self, link):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, ReviewTab) and getattr(w, 'link', None) == link:
                self.tabs.setCurrentIndex(i)
                return
        tab = ReviewTab(self.profile, link, self)
        n = sum(1 for i in range(self.tabs.count()) if isinstance(self.tabs.widget(i), ReviewTab)) + 1
        idx = self.tabs.addTab(tab, f'复盘 {n}')
        self.tabs.setCurrentIndex(idx)
        self._add_close_button(tab)
        tab.label_changed.connect(lambda t, tb=tab: self.tabs.setTabText(self.tabs.indexOf(tb), t))
        tab.captured.connect(lambda r, tb=tab: self.on_report(r, tb.link))
        return tab

    def _add_close_button(self, tab):
        """关闭按钮外面包一层带右边距的容器，保证完全落在标签内部"""
        btn = QToolButton()
        btn.setObjectName('tabclose')
        btn.setIcon(QIcon(theme.close_pixmap(self.p, 12)))
        btn.setIconSize(QSize(12, 12))
        btn.setFixedSize(16, 16)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip('关闭')
        btn.clicked.connect(lambda _=False, t=tab: self.close_tab(self.tabs.indexOf(t)))

        holder = QWidget()
        holder.setStyleSheet('background: transparent;')
        hb = QHBoxLayout(holder)
        hb.setContentsMargins(0, 2, 7, 0)
        hb.setSpacing(0)
        hb.addWidget(btn)

        idx = self.tabs.indexOf(tab)
        self.tabs.tabBar().setTabButton(idx, QTabBar.ButtonPosition.RightSide, holder)
        self._close_buttons[tab] = btn

    def _refresh_close_buttons(self):
        for tab, btn in getattr(self, '_close_buttons', {}).items():
            btn.setIcon(QIcon(theme.close_pixmap(self.p, 12)))

    def close_tab(self, idx):
        if idx <= 0:
            return
        w = self.tabs.widget(idx)
        self._close_buttons.pop(w, None)
        self.tabs.removeTab(idx)
        if w:
            w.deleteLater()

    def on_report(self, rid, link=''):
        self.record_tab.add_pending(rid, link)
        # 正在看复盘页时不抢焦点，避免多份同时出报告时来回跳
        from ui.review import ReviewTab as _RT
        if not isinstance(self.tabs.currentWidget(), _RT):
            self.tabs.setCurrentIndex(0)

    # ---------- 文件
    def open_path(self, path):
        shell_open(path)

    # ---------- 剪贴板
    def event(self, ev):
        if ev.type() == QEvent.WindowActivate:
            self._peek_clipboard()
        return super().event(ev)

    def _peek_clipboard(self):
        if self.record_tab.ed_link.toPlainText().strip():
            return
        try:
            txt = (QGuiApplication.clipboard().text() or '').strip()
        except Exception:
            return
        if re.search(r'https?://', txt):
            self.record_tab.ed_link.setPlainText(txt[:400])
            self.record_tab.status.setText('已从剪贴板填入牌谱链接。')


def set_app_icon(app):
    """标题栏/任务栏图标：优先用 .ico，其次 512 的 png。"""
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('mahjong.record.qt.1')
        except Exception:
            pass
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    for name in (os.path.join(base, 'mahjong.ico'),
                 os.path.join(base, 'icons', 'mahjong_512.png'),
                 os.path.join(base, 'icons', 'mahjong.png')):
        if os.path.exists(name):
            icon = QIcon(name)
            if not icon.isNull():
                app.setWindowIcon(icon)
                return


def main():
    log_file = core.setup_logging()

    def hook(exc_type, exc, tb_obj):
        core.log().error('未捕获异常', exc_info=(exc_type, exc, tb_obj))
        QMessageBox.critical(None, '出错了', f'{exc}\n\n日志：{log_file}')

    sys.excepthook = hook
    core.log().info('---- 麻将记录 %s 启动，日志 %s ----', core.VERSION, log_file)
    app = QApplication(sys.argv)
    app.setApplicationName('麻将记录')
    app.setStyle('Fusion')
    set_app_icon(app)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
