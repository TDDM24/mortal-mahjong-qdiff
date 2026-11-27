# -*- coding: utf-8 -*-
"""业务层：路径、计算、落盘、只读、Excel 读取。不含任何界面代码。

tkinter 版（mrapp.py）和 Qt 版（main_qt.py）都从这里取数据，保证数字一致。
"""
import datetime
import json
import logging
import os
import re
import sys
import time
import urllib.error

IS_MAC = sys.platform == 'darwin'
IS_WIN = os.name == 'nt'
FROZEN = bool(getattr(sys, 'frozen', False))

MODE = 'self'
VERSION = 'v1.0.0'   # 2026-11-28 第二轮审计修复
HON = {'E': '东', 'S': '南', 'W': '西', 'N': '北', 'P': '白', 'F': '發', 'C': '中'}
DEFAULT_LINES = [('合计失分', 10, 7), ('每100次牌效决策', 13, 8), ('每100次防守决策', 14, 10),
                 ('压力分数', 16, 11), ('严重失误', 2.3, 1.0)]
LINES = [tuple(x) for x in DEFAULT_LINES]
LINES_ON = False      # 没手动设置过就不显示维持线/检查点


def set_lines(lines, on=None):
    """自定义检查点：MainWindow 启动时从 settings.json 读进来。"""
    global LINES, LINES_ON
    if on is not None:
        LINES_ON = bool(on)
    out = []
    for item in lines:
        try:
            out.append((str(item[0]), float(item[1]), float(item[2])))
        except Exception:
            continue
    if len(out) == len(DEFAULT_LINES):
        LINES = out


def line_state(name, value):
    """这张牌该标红还是标绿：超维持线=bad，达检查点=good。"""
    if not LINES_ON or value is None:
        return ''
    for n, keep, goal in LINES:
        if n == name:
            if value > keep:
                return 'bad'
            if value <= goal:
                return 'good'
    return ''


_LOG_DIR = None


def log_dir():
    """日志放哪：先试程序目录，不行退回用户目录。"""
    global _LOG_DIR
    if _LOG_DIR:
        return _LOG_DIR
    for cand in (os.path.join(HERE, 'logs'),
                 os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                              '麻将记录', 'logs')):
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, '.w')
            with open(probe, 'w') as f:
                f.write('x')
            os.remove(probe)
            _LOG_DIR = cand
            return cand
        except Exception:
            continue
    _LOG_DIR = HERE
    return _LOG_DIR


def setup_logging():
    """滚动日志：单文件 1MB，留 3 份。返回日志路径。"""
    from logging.handlers import RotatingFileHandler
    path = os.path.join(log_dir(), 'app.log')
    root = logging.getLogger()
    if not root.handlers:
        root.setLevel(logging.INFO)
        fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S')
        try:
            fh = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except Exception:
            pass
        try:
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            root.addHandler(sh)
        except Exception:
            pass
    return path


def log():
    return logging.getLogger('mahjong')


def _resolve_paths():
    here = os.path.dirname(os.path.abspath(__file__))
    if os.environ.get('MAHJONG_HOME'):
        base = os.path.abspath(os.path.expanduser(os.environ['MAHJONG_HOME']))
    elif FROZEN and IS_MAC:
        base = os.path.expanduser('~/Documents/麻将记录')
    elif FROZEN:
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(here) if os.path.basename(here) == '程序' else here
        return base, here
    return base, os.path.join(base, '程序')


BASE, HERE = _resolve_paths()
PATH_FALLBACK = ''
try:
    os.makedirs(HERE, exist_ok=True)
    with open(os.path.join(HERE, '.write_test'), 'w') as _f:
        _f.write('x')
    os.remove(os.path.join(HERE, '.write_test'))
except Exception:
    import tempfile
    _alt = os.path.join(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(),
                        '麻将记录', '程序')
    try:
        os.makedirs(_alt, exist_ok=True)
        HERE = _alt
        BASE = os.path.dirname(_alt)
        PATH_FALLBACK = f'程序目录不可写，已改用 {BASE}'
    except Exception:
        pass
if HERE not in sys.path:
    sys.path.append(HERE)
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mr        # noqa: E402
import effaudit  # noqa: E402

mr.CACHE = os.path.join(HERE, 'reports')
XLSX = os.path.join(BASE, '麻将逐场数据.xlsx')
DATA = os.path.join(HERE, '牌谱数据')


# ---------------------------------------------------------------- 小工具
def get_rid(text):
    m = re.search(r'([0-9a-f]{16})', (text or '').strip())
    return m.group(1) if m else None


def esc(v):
    """拼进 HTML 的外部字段一律过一遍。报告 JSON 是外部文件，可以带任意字符。"""
    return (str('' if v is None else v)
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&#39;'))


def tname(t):
    if t in HON:
        return HON[t]
    return ('0' + t[1]) if t.endswith('r') else t


def hand_str(tiles):
    g = {'m': [], 'p': [], 's': []}
    hon = []
    for t in sorted(tiles, key=mr.tile_index):
        if t in HON:
            hon.append(HON[t])
        else:
            g[t[1]].append('0' if t.endswith('r') else t[0])
    return ' '.join([''.join(v) + k for k, v in g.items() if v] + ([''.join(hon)] if hon else []))


def act_str(a):
    if a.get('type') == 'dahai':
        return ('摸切 ' if a.get('tsumogiri') else '') + tname(a.get('pai', ''))
    return mr.act_cn(a)


def fmt5(name, v):
    if v is None:
        return '—'
    return f'{v:.2f}' if name in ('合计失分', '严重失误') else f'{v:.1f}'


def verdict(five):
    if MODE != 'self' or not LINES_ON:
        return ''
    over = sum(1 for (n, keep, goal), (v, _) in zip(LINES, five) if v is not None and v > keep)
    good = sum(1 for (n, keep, goal), (v, _) in zip(LINES, five) if v is not None and v <= goal)
    parts = []
    if over:
        parts.append(f'超维持线 {over} 项')
    if good:
        parts.append(f'达检查点 {good} 项')
    return '，'.join(parts) or '都在线内'


def verdict_short(five):
    """表格里用的短判定：超2 达1 / 在线内"""
    if MODE != 'self' or not LINES_ON:
        return ''
    over = sum(1 for (n, keep, goal), (v, _) in zip(LINES, five) if v is not None and v > keep)
    good = sum(1 for (n, keep, goal), (v, _) in zip(LINES, five) if v is not None and v <= goal)
    if over and good:
        return f'超{over} 达{good}'
    if over:
        return f'超{over}'
    if good:
        return f'达{good}'
    return '在线内'


def excel_is_open():
    """Excel 打开时会建 ~$ 锁文件；我们自己设的只读属性不算被占用。"""
    if os.path.exists(os.path.join(BASE, '~$' + os.path.basename(XLSX))):
        return True
    if not os.path.exists(XLSX) or mr.is_readonly(XLSX):
        return False
    try:
        with open(XLSX, 'r+b'):
            pass
    except PermissionError:
        return True
    except FileNotFoundError:
        return False
    return False


# ---------------------------------------------------------------- 计算
def compute(rid):
    """取报告并算。404 时先重试几次——同时提交多份时，后几份常还没生成好。"""
    # 报告先过结构校验：三麻/缺字段直接抛人话，别让上层拿到半截数据
    d = None
    for attempt in range(4):
        try:
            d = mr.load_report(rid)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 404 and attempt < 3:
                time.sleep(2)
                continue
            if exc.code == 404:
                raise RuntimeError('报告还没生成好（404）。等网站跑完再试，或这份报告已过期。') from exc
            raise
        except urllib.error.URLError as exc:
            raise RuntimeError(f'取报告失败：{exc.reason}') from exc
    mr.verify_report(d)
    target = d['player_id']
    rows = mr.analyze(d)
    s = mr.summary(rows)
    score, rank = mr.final_scores(d)
    ls = mr.log_stats(d)
    pr = mr.pressure(rows, target)
    eff = s['牌效_raw'] / s['牌效_n'] * 100 if s['牌效_n'] else None
    dfn = s['防守_raw'] / s['防守_n'] * 100 if s['防守_n'] else None
    five = [(s['loss'], ''), (eff, f'{s["牌效_n"]} 次'), (dfn, f'{s["防守_n"]} 次'),
            (pr['merged']['per100'], f'{pr["merged"]["n"]} 次'),
            (s['severe'], f'{round(s["severe"] * s["n"] / 100)} 次')]
    return dict(rid=rid, d=d, target=target, rows=rows, s=s, score=score, rank=rank, ls=ls, pr=pr,
                rating=d['review']['rating'] * 100, five=five, lobby=mr.report_meta(d)['lobby'])


def top_rows(g, n=10):
    return sorted(g['rows'], key=lambda x: -x['diff'])[:n]


def row_html(r, target):
    """一手错牌的 HTML 片段（详情窗口和 md 共用）。"""
    st = r['entry']['state']
    sh = mr.shanten(st['tehai'], len(st.get('fuuros') or []))
    diff_cls = 'bad' if r['diff'] >= 1.0 else 'h3'
    ea = ee = ''
    if r['cat'] == '防守' and r['snap']:
        ea = '，' + (mr.worst_safety(r['snap'], target, mr.tile_index(r['actual']['pai']))[1] or '')
        if r['expected'].get('type') == 'dahai':
            ee = '，' + (mr.worst_safety(r['snap'], target, mr.tile_index(r['expected']['pai']))[1] or '')
    return (
        f'<p><span class="h3">{esc(mr.kyoku_name(r["snap"]))} · {r["junme"]} 巡　[{esc(r["cat"])}]　</span>'
        f'<span class="{diff_cls}">差 {r["diff"]:.2f}</span><br>'
        f'<span class="dim">手牌　</span>{esc(hand_str(st["tehai"]))}<span class="dim">（{sh} 向听）</span><br>'
        f'<span class="dim">你　　</span>{esc(act_str(r["actual"]))}（Q {r["q_actual"]:.2f}{esc(ea)}）<br>'
        f'<span class="dim">Mortal　</span><span class="mortal">{esc(act_str(r["expected"]))}'
        f'（Q {r["q_expected"]:.2f}{esc(ee)}）</span></p>')


def game_html(g, top=10):
    s, pr, ls = g['s'], g['pr'], g['ls']
    def _row(name, keep, goal, v, n):
        state = line_state(name, v)
        cls = 'v ' + state if state else 'v'
        note = f'（{n}）' if n and v is not None else ''
        tail = (f'<td class="dim">≤{keep}</td><td class="dim">≤{goal}</td>'
                if LINES_ON else '')
        return (f'<tr><td class="k">{name}</td><td class="{cls}">{fmt5(name, v)}'
                f'<span class="dim">{note}</span></td>{tail}</tr>')

    five_rows = ''.join(_row(name, keep, goal, v, n)
                        for (name, keep, goal), (v, n) in zip(LINES, g['five']))
    sl_rows = ''.join(row_html(r, g['target']) for r in top_rows(g, top))
    return f"""
<div class="h1">第 {int(g['rank'])} 位　{int(g['score'])} 点{'　' + esc(g['lobby']) + '卓' if g['lobby'] else ''}　rating {g['rating']:.1f}　{s['n']} 手</div>
<div class="dim">报告 {esc(g['rid'])}</div>
<div class="h2">重点 5 项</div>
<table class="five">
<tr><th>项目</th><th>本场</th>{'<th>维持线</th><th>检查点</th>' if LINES_ON else ''}</tr>{five_rows}
</table>
<p><span class="h2">辅助　</span>牌效 {s['牌效']:.2f} · 防守 {s['防守']:.2f} · 副露压力下 {s['副露压力下']:.2f}
 · 立直 {s['立直判断']:.2f} · 鸣牌 {s['鸣牌判断']:.2f}</p>
<p><span class="h2">战绩　</span>和了 {ls['win_rate']:.1f}% · 放铳 {ls['deal_rate']:.1f}%
 · 立直 {ls['riichi_rate']:.1f}% · 副露 {ls['meld_rate']:.1f}%</p>
<p><span class="h2">压力　</span>立直威胁 {pr['riichi']['per100']:.1f}（{pr['riichi']['n']} 次）
 · 隐形威胁 {pr['hidden']['per100']:.1f}（{pr['hidden']['n']} 次）
 · 无威胁 {pr['none']['per100']:.1f}（{pr['none']['n']} 次）</p>
<div class="h2">Q 差最大的 {top} 手</div>{sl_rows}
"""


def game_md(g, link='', note=''):
    L = [f'# 第 {g["rank"]} 位 {g["score"]} 点 · rating {g["rating"]:.1f}', '',
         f'- 报告：<https://mjai.ekyu.moe/killerducky/?data=/report/{g["rid"]}.json>',
         f'- 原始数据：`{g["rid"]}.json`']
    if link:
        L.append(f'- 牌谱：<{link}>')
    if note:
        L.append(f'- 备注：{note}')
    L += ['', '## 重点 5 项', '', '| 项目 | 本场 | 维持线 | 检查点 |', '|---|---|---|---|']
    for (name, keep, goal), (v, n) in zip(LINES, g['five']):
        L.append(f'| {name} | {fmt5(name, v)}' + (f'（{n}）' if n and v is not None else '')
                 + f' | ≤{keep} | ≤{goal} |')
    s, ls, pr = g['s'], g['ls'], g['pr']
    L += ['', f'- 辅助：牌效 {s["牌效"]:.2f}、防守 {s["防守"]:.2f}、副露压力下 {s["副露压力下"]:.2f}、'
              f'立直 {s["立直判断"]:.2f}、鸣牌 {s["鸣牌判断"]:.2f}',
          f'- 战绩：和了 {ls["win_rate"]:.1f}%、放铳 {ls["deal_rate"]:.1f}%、'
          f'立直 {ls["riichi_rate"]:.1f}%、副露 {ls["meld_rate"]:.1f}%',
          f'- 压力：立直威胁 {pr["riichi"]["per100"]:.1f}（{pr["riichi"]["n"]} 次）、'
          f'隐形威胁 {pr["hidden"]["per100"]:.1f}（{pr["hidden"]["n"]} 次）',
          '', '## Q 差最大的 10 手', '', '| # | 局 · 巡 | 类别 | 手牌 | 你 | Mortal | 差 |', '|---|---|---|---|---|---|---|']
    for i, r in enumerate(top_rows(g, 10), 1):
        L.append(f'| {i} | {mr.kyoku_name(r["snap"])} · {r["junme"]} | {r["cat"]} | '
                 f'{hand_str(r["entry"]["state"]["tehai"])} | {act_str(r["actual"])}（{r["q_actual"]:.2f}） | '
                 f'{act_str(r["expected"])}（{r["q_expected"]:.2f}） | {r["diff"]:.2f} |')
    return '\n'.join(L) + '\n'


def _data_dir():
    """每场的 .md/.json 存这里：先试程序目录，不行退回用户目录（报告 15 天就过期，必须留档）"""
    for cand in (DATA, os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'),
                                    '麻将记录', '牌谱数据')):
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, '.write_test')
            with open(probe, 'w') as f:
                f.write('x')
            os.remove(probe)
            return cand
        except Exception:
            continue
    return DATA


def save_game_files(g, link, note):
    global DATA
    DATA = _data_dir()
    log, tw, when, lobby = mr.tenhou_info(link)
    stem = (when.replace(' ', '_').replace(':', '') + '_' if when else '') + g['rid']
    md = os.path.join(DATA, stem + '.md')
    with open(md, 'w', encoding='utf-8') as f:
        f.write(game_md(g, link, note))
    with open(os.path.join(DATA, stem + '.json'), 'w', encoding='utf-8') as f:
        json.dump(g['d'], f, ensure_ascii=False)
    return os.path.relpath(md, BASE).replace(os.sep, '/')


# ---------------------------------------------------------------- 已记录场次
def time_key(log, date, no):
    m = re.match(r'(\d{10})gm', log or '')
    if m:
        return m.group(1) + f'{int(no or 0):04d}'
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:\D+(\d{1,2}))?', date or '')
    if m:
        return f'{m.group(1)}{m.group(2)}{m.group(3)}{int(m.group(4) or 0):02d}{int(no or 0):04d}'
    m = re.match(r'(\d{1,2})/(\d{1,2})(?:\s*(\d{1,2}))?', date or '')
    if m:
        import datetime as _dt
        year = _dt.date.today().year      # 旧格式没有年份，按当年算（跨年旧数据会靠序号兜底）
        return f'{year}{int(m.group(1)):02d}{int(m.group(2)):02d}{int(m.group(3) or 0):02d}{int(no or 0):04d}'
    return f'9{int(no or 0):013d}'


def recorded_games():
    import store
    return store.games_for_audit()


def record_one(rid, link='', note=''):
    """算一场 + 存 md/json + 写库。返回 (g, 序号, 是否已存在)。"""
    import store
    log().info('记录开始 rid=%s link=%s', rid, link or '-')
    g = compute(rid)
    try:
        g['saved_md'] = save_game_files(g, link, note)
    except Exception as exc:
        g['save_error'] = str(exc)
    row = mr.build_row(g, link, note)
    no, existed = store.add_row(row)
    log().info('记录完成 rid=%s seq=%s existed=%s', rid, no, existed)
    return g, no, existed


# ---------------------------------------------------------------- 牌效审计
def audit(picked, progress=None, should_stop=None):
    """picked: recorded_games() 的元素；返回 (汇总, 失败标签列表)。"""
    games, failed = [], []
    for i, gm in enumerate(picked):
        if should_stop and should_stop():
            break
        label = f'#{gm["no"]}'
        if progress:
            progress(i, len(picked), f'牌效审计：{i + 1}/{len(picked)} 场（第 {gm["no"]} 行）')
        try:
            rep = mr.load_report(gm['rid'])
        except Exception:
            failed.append(label)
            continue
        n, ne, le, hands = effaudit.classify_report(rep)
        for h in hands:
            h['game'] = label
        games.append((label, n, ne, le, hands))
    return effaudit.summarize(games), failed


def audit_html(res, failed):
    out = [f'<div class="h1">牌效审计　{res["games"]} 场　{res["n"]} 手决策</div>']
    out.append(f'<p class="dim">牌效决策 {res["ne"]} 次，牌效失分 {res["le"]:.1f}'
               f'（每 100 手 {res["le"] / max(1, res["n"]) * 100:.2f}）</p>')
    if failed:
        out.append(f'<p class="bad">没取到报告、已跳过：{"、".join(failed)}</p>')
    out.append('<table class="grid"><tr><th>类别</th><th>手数</th><th>失分</th><th>占牌效</th><th>Q差≥1</th></tr>')
    for c in sorted(res['cats'], key=lambda c: -c['loss']):
        cls = ' class="bad"' if c['big'] >= 3 else ''
        out.append(f'<tr{cls}><td>{c["k"]}</td><td>{c["n"]}</td><td>{c["loss"]:.1f}</td>'
                   f'<td>{c["share_eff"]:.1f}%</td><td>{c["big"]}</td></tr>')
    out.append('</table>')
    out.append('<div class="h2">按打牌前的向听（各类失分）</div>')
    names = {'Mortal 宁可少进张': 'M宁可少进张'}
    out.append('<table class="grid"><tr><th>向听</th>' +
               ''.join(f'<th>{names.get(k, k)}</th>' for k in effaudit.CATS) + '<th>合计</th></tr>')
    for sh in sorted(res['bysh']):
        cnt = res['bysh'][sh]
        lab = '听牌' if sh == 0 else (f'{sh} 向听' if sh < 4 else '4 向听+')
        vals = [cnt.get(k, 0) for k in effaudit.CATS]
        out.append(f'<tr><td>{lab}</td>' +
                   ''.join(f'<td>{v:.1f}</td>' if v else '<td class="dim">·</td>' for v in vals) +
                   f'<td>{sum(vals):.1f}</td></tr>')
    out.append('</table>')
    out.append('<div class="h2">各类最大的几手</div>')
    for k in effaudit.CATS:
        hs = sorted([h for h in res['hands'] if h['k'] == k], key=lambda h: -h['diff'])[:4]
        if not hs:
            continue
        out.append(f'<div class="h3">【{k}】</div>')
        for h in hs:
            out.append(
                f'<p><span class="{"bad" if h["diff"] >= 1 else "h3"}">{esc(h.get("game", ""))} '
                f'{h["kyoku"]} · {h["junme"]} 巡　差 {h["diff"]:.2f}</span><br>'
                f'<span class="dim">手牌　</span>{esc(hand_str(h["hand"]))}<br>'
                f'<span class="dim">你　　</span>{esc(act_str(h["a"]))}（{h["sa"]} 向听，进张 {h["ua"]}）<br>'
                f'<span class="dim">Mortal　</span><span class="mortal">{esc(act_str(h["x"]))}'
                f'（{h["sx"]} 向听，进张 {h["ux"]}）</span></p>')
    return '\n'.join(out)


def guide_html():
    def term(t, d):
        return f'<p><span class="term">{t}</span><br>{d}</p>'
    L = [f'<div class="h1">麻将记录 {VERSION} · 使用说明</div>',
         '<div class="h2">一、怎么用</div>',
         '<p>① 在「记录」标签粘贴牌谱链接（天凤 / 雀魂）。</p>',
         '<p>② 点「复盘」：会新开一个标签，自动把链接填进网页输入框；你过验证码、点提交。</p>',
         '<p>③ 报告出来时，标签标题会变成报告 id，程序自动抓取并回到「记录」标签，填好 id。</p>',
         '<p>④ 点「记录一场」：写进本地数据库，同时把这场存成 .md/.json（报告 15 天会过期，'
         '本地这份是以后还能复盘审计的唯一凭据）；想用 Excel 分析时点「导出 Excel」。</p>',
         '<p>⑤ 「只看数字」不写表；「牌效审计」按勾选的场次做分类统计。</p>',
         '<p>⑥ 原始数据存在本地数据库（麻将记录.db），不再依赖 Excel 打开；'
         'Excel 只是导出用的副本，随便改都不会影响库里的数据。</p>',
         '<div class="h2">二、名词解释</div>',
         term('Q 值 / Q 差', 'Mortal 对每个候选打法的估值。Q 差 = 最优那张的 Q 减去你打的那张的 Q。'),
         term('rating', 'Mortal 给整场的评分，满分 100。'),
         term('合计失分', 'Σ Q 差 ÷ 决策数 × 100。'),
         term('严重失误', 'Q 差 ≥ 1.0 的决策，每 100 次决策里有几次。'),
         term('每100次牌效决策', '牌效决策（没人立直、他家没两组以上副露时的切牌）的失分 ÷ 次数 × 100。'),
         term('每100次防守决策', '他家有人立直时的切牌失分 ÷ 次数 × 100。'),
         term('副露压力下', '没人立直，但他家有人吃/碰两组以上时的切牌。'),
         term('压力分数', '立直威胁 + 隐形威胁两类局面里，每 100 次切牌的失分。'),
         term('隐形威胁', '没人立直，但对手里至少有一家其实已经听牌了——比如默听（dama），'
                       '或者副露之后已经听牌。危险是真实存在的，只是对手没有宣告，所以叫「隐形」。'),
         term('检查点', '可以自己设定的一组目标值（使用凤卓数据计算得出）。'
                       '点「检查点设置」打开开关后，报告里会多出「维持线 / 检查点」两列：'
                       '超过线标红、达到目标标绿；不开启就不显示。'),
         '<div class="h2">三、牌效审计的分类</div>',
         term('该进没进 / 该退没退', 'Mortal 那张能进向听而你没进；或 Mortal 退向听求好形而你没退。'),
         term('进张算少', '向听相同，Mortal 那张进张多 2 张以上。'),
         term('Mortal 宁可少进张', '向听相同，Mortal 那张进张反而少，为了好形 / 打点 / 役。'),
         term('改良没看见', '向听、进张都差不多，但 Mortal 那张之后靠改良能多出的进张明显更多。'),
         term('其他', '打点、役、宝牌、安全度等原因，或程序判断不了的。'),
         f'<p class="dim">数据目录：{BASE}</p>']
    return '\n'.join(L)
