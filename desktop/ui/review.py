# -*- coding: utf-8 -*-
"""复盘标签：内嵌 QtWebEngine，自动把牌谱链接填进网页输入框，抓到报告 id 就发信号。"""
import json
import re

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

START_URL = 'https://mjai.ekyu.moe/zh-cn.html'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36')

# 优先找「牌谱 / log / url」字样的可见输入框，找不到就退化成第一个可见输入框
# 先强制切回「牌谱 URL」模式（否则可能停在别的输入方式/派遣个室），再填值并滚回顶部
FILL_JS = """
(function(text){
  // 1) 切回「牌谱 URL」
  try {
    const radio = document.querySelector('input[name="input-method"][value="log-url"]');
    if (radio && !radio.checked) {
      radio.checked = true;
      radio.dispatchEvent(new Event('change', {bubbles:true}));
      if (typeof window.changeInputMethod === 'function') window.changeInputMethod('log-url');
    }
  } catch (e) {}

  // 2) 找输入框：优先 log-url
  let el = document.querySelector('input[name="log-url"]');
  if (!el) {
    const ok = ['hidden','checkbox','radio','submit','button','file'];
    const els = Array.from(document.querySelectorAll('input, textarea'))
        .filter(e => e.offsetParent !== null && !ok.includes((e.type||'').toLowerCase()));
    if (!els.length) return 'no-input';
    const score = e => (/牌谱|谱|log|url|对局|牌局/i.test((e.placeholder||'') + (e.name||'') + (e.id||'')) ? 2 : 0);
    els.sort((a,b) => score(b) - score(a));
    el = els[0];
  }

  // 3) 填值
  el.focus();
  el.value = text;
  el.dispatchEvent(new Event('input', {bubbles:true}));
  el.dispatchEvent(new Event('change', {bubbles:true}));

  // 4) 别让 focus 把页面滚到别处（之前会滚到「派遣个室」）
  try { window.scrollTo(0, 0); } catch (e) {}
  return 'filled:' + (el.name || el.id || el.type || 'input');
})(%s)
"""


class ReviewTab(QWidget):
    captured = Signal(str)       # 报告 id
    label_changed = Signal(str)  # 标签标题

    def __init__(self, profile: QWebEngineProfile, link: str = '', parent=None):
        super().__init__(parent)
        self.link = link
        self._captured = set()
        self._auto_filled = False
        self._in_flight = False       # 正在执行 fill()，防止 loader 进度与定时器同时打进来
        self._last_load_url = ''      # 上一次真正加载完成的 URL，用来区分「换页」和「同页跳转」
        self._tries = 0
        self._title = '复盘'

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        self.btn_back = QPushButton('后退')
        self.btn_forward = QPushButton('前进')
        self.btn_reload = QPushButton('刷新')
        self.btn_fill = QPushButton('填入牌谱')
        self.url_label = QLabel('')
        self.url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        for b, w in ((self.btn_back, 60), (self.btn_forward, 60), (self.btn_reload, 64), (self.btn_fill, 88)):
            b.setFixedWidth(w)
            bar.addWidget(b)
        bar.addWidget(self.url_label, 1)

        self.view = QWebEngineView(self)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.page = QWebEnginePage(profile, self.view)
        self.view.setPage(self.page)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addLayout(bar)
        lay.addWidget(self.view, 1)

        self.btn_back.clicked.connect(self.view.back)
        self.btn_forward.clicked.connect(self.view.forward)
        self.btn_reload.clicked.connect(self.view.reload)
        self.btn_fill.clicked.connect(self.fill)
        self.view.urlChanged.connect(self._on_url)
        self.view.titleChanged.connect(self._on_title)

        self.view.loadFinished.connect(self._on_load)
        self.view.loadProgress.connect(self._on_progress)
        # 兜底：有的环境下 loadFinished 迟迟不来（缓存目录不可写等），用定时器盯着
        self._watch = QTimer(self)
        self._watch.setInterval(1500)
        self._watch.timeout.connect(self._auto_fill)
        self._watch.start()
        start = self.link if re.match(r'^https?://', self.link or '') and 'mjai.ekyu.moe' in self.link else START_URL
        QTimer.singleShot(0, lambda: self.view.setUrl(QUrl(start)))

    def _on_progress(self, p):
        if p >= 40 and not self._auto_filled:
            self._auto_fill()

    def _on_load(self, ok):
        if ok and self._looks_like_link():
            # 只在真正换了页面时重置；同一页里的锚点跳转不该把已填状态清掉
            if self.view.url().toString() != self._last_load_url:
                self._last_load_url = self.view.url().toString()
                self._auto_filled = False
                self._tries = 0
                self._in_flight = False
            QTimer.singleShot(600, self._auto_fill)     # 等表单渲染出来再填

    def _looks_like_link(self):
        return bool(self.link) and bool(re.search(r'https?://|tenhou|paipu|majsoul', self.link, re.I))

    def _auto_fill(self):
        if self._auto_filled or self._in_flight or not self._looks_like_link():
            return
        self._in_flight = True
        self.fill()

    # ---------- 操作
    def fill(self):
        if not self._looks_like_link():
            self.url_label.setText('这个输入框里有内容，但不像牌谱链接；只填链接，不填报告 id')
            return
        self._in_flight = True
        self.page.runJavaScript(FILL_JS % json.dumps(self.link, ensure_ascii=False), 0, self._filled)

    def _filled(self, result):
        self._in_flight = False
        msg = str(result)
        if msg.startswith('no-input'):
            self._tries = getattr(self, '_tries', 0) + 1
            if self._tries <= 6:
                self._in_flight = False
                self.url_label.setText(f'页面还没渲染好，{self._tries} 秒后重试…')
                QTimer.singleShot(1000 * self._tries, self._auto_fill)
            else:
                self.url_label.setText('没找到输入框，请手动粘贴（或点「填入牌谱」）')
        else:
            self._auto_filled = True
            self._tries = 0
            if getattr(self, '_watch', None) is not None:
                self._watch.stop()
            self.url_label.setText('已填入网页输入框')

    # ---------- 事件
    def _on_title(self, title):
        if title:
            self._title = title[:28]
            if not self._captured:
                self.label_changed.emit(self._title)

    def _on_url(self, url: QUrl):
        s = url.toString()
        self.url_label.setText(s)
        host = (url.host() or '').lower()
        trusted = host.endswith('mjai.ekyu.moe') or host.endswith('tenhou.net') or host.endswith('mahjongsoul.com')
        m = re.search(r'report/([0-9a-f]{16})', s, re.I)
        if m is None and trusted:
            m = re.search(r'(?<![0-9a-zA-Z])([0-9a-f]{16})(?![0-9a-zA-Z])', s, re.I)
        if m and m.group(1) not in self._captured:
            rid = m.group(1)
            self._captured.add(rid)
            self.label_changed.emit('报告 ' + rid[:8])
            self.captured.emit(rid)
