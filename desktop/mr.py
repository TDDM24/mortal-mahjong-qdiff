#!/usr/bin/env python3
"""mr.py — 一场段位战的全部复盘数据，只用 Python 标准库，不需要浏览器、不需要装包。

用法示例
    python3 mr.py 92d24862f6890e80                # 5 项 + 辅助 + 压力分数
    python3 mr.py 92d24862f6890e80 --top 5        # 再加 Q 差前 5 手（含手牌、候选、安全度）
    python3 mr.py --log 92d24862f6890e80          # 只出和了率/放铳率/立直率/副露率（读报告里的 mjai_log）
    python3 mr.py 92d24862f6890e80 --row          # 输出逐场总表的一行（粘到表尾）
    python3 mr.py --batch 对局目录.md             # 文件里出现的所有报告 id 批量跑
    python mr.py 报告id --xlsx 麻将逐场数据.xlsx --tenhou "天凤链接"   # 在 Excel 末尾追加一行（需要 pip install openpyxl）
          可选：--note "备注"  --state "深夜"（不写就按牌谱编号判断上级 / 一般卓）
          同一个报告 id 已经在表里时不会重复写；Excel 正开着这个文件时写不进去，先关掉

设计说明
    · 报告 JSON（mjai.ekyu.moe/report/<id>.json）里已经有 Mortal 每手所有候选的 Q 值，
      "失分"这类指标全部由 Q 值算出，所以不需要浏览器。
    · 报告只保留 15 天；第一次取到后存进 ./reports/，之后一直用缓存，过期也不影响。
    · 需要新牌谱时仍然要在浏览器提交一次（Mortal 跑在他们的服务器上）。

口径（与《00_当前状态》《规则/统计口径》一致）
    合计失分     = Σ(Mortal 最优 Q − 你打的 Q) × 100 ÷ 决策数
    严重失误     = Q 差 ≥ 1.0 的手数 ÷ 决策数 × 100
    每100次牌效决策 = 牌效失分 ÷ 牌效决策次数 × 100
    每100次防守决策 = 防守失分 ÷ 防守决策次数 × 100
    压力分数     = 没人立直但他家已实际听牌时的切牌失分 ÷ 该类切牌次数 × 100

修订记录
    2026-11-18  加杠（kakan）把原来的碰升级成杠，不再记成新的一组副露。以前上家碰了再加杠会被数成
                两组：① 他会被误判成"副露压力下"；② 他的听牌判定拿错副露数，漏掉隐形威胁。
                影响：只有出现过加杠的牌谱（11/15 15 时②：牌效决策 9.6→10.2、压力 11.9→13.9），
                其余已核对的牌谱数字完全不变。
    2026-11-24  加 --xlsx：把一场的全部数字追加到 Excel 数据文件末尾（只追加一行，不改已有行），
                压力分项（立直威胁、隐形威胁的次数 / 失分 / sq）、和了率、放铳率一起写进去。
    2026-11-18  --log 改为接收 Mortal 报告 id（天凤原始 JSON 不是 mjai 格式，读不了；旧的正则也写错了）。
"""

import json
import os
import re
import sys
import urllib.request
from collections import Counter

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')
UA = {'User-Agent': 'Mozilla/5.0'}
HONORS = ['E', 'S', 'W', 'N', 'P', 'F', 'C']
SUITS = 'mps'


def _force_utf8_console():
    """Windows 控制台默认是 GBK / CP932 之类，直接 print 中文会崩；macOS、Linux 本来就是 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass


_force_utf8_console()


def _urlopen(url):
    """下载报告。macOS 上 python.org 版 Python 经常报证书错误，装了 certifi 就用它的证书再试一次。"""
    req = urllib.request.Request(url, headers=UA)
    try:
        return urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.URLError as exc:
        if 'CERTIFICATE_VERIFY_FAILED' not in str(exc) and 'certificate' not in str(exc).lower():
            raise
        try:
            import ssl
            import certifi
        except ImportError:
            raise RuntimeError(
                '连不上 mjai.ekyu.moe：本机 Python 缺少根证书。\n'
                'macOS：先运行 /Applications/Python 3.12/Install Certificates.command（把 3.12 换成你的版本）。'
            ) from exc
        ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(req, timeout=60, context=ctx).read()


def tile_index(t):
    """'?' 是单视角牌谱里的未知暗牌，返回 -1，调用方要跳过。"""
    if not t or t == '?':
        return -1
    t = t.replace('r', '')
    if t in HONORS:
        return 27 + HONORS.index(t)
    return {'m': 0, 'p': 9, 's': 18}[t[-1]] + int(t[:-1]) - 1


def tile_name(i):
    if i >= 27:
        return HONORS[i - 27]
    return f'{i % 9 + 1}{SUITS[i // 9]}'


def parse_tile(t):
    t = t.replace('r', '')
    if t in HONORS:
        return 'z', HONORS.index(t) + 1
    return t[-1], int(t[:-1])


def dora_from_indicator(ind):
    s, n = parse_tile(ind)
    if s == 'z':
        return HONORS[{1: 2, 2: 3, 3: 4, 4: 1, 5: 6, 6: 7, 7: 5}[n] - 1]
    return f'{n + 1 if n < 9 else 1}{s}'


def _shanten_std(counts, melds):
    best = 8
    c = counts

    def dfs(i, m, t, h):
        nonlocal best
        while i < 34 and c[i] == 0:
            i += 1
        if i >= 34:
            mm = m + melds
            tt = min(t, max(0, 4 - mm))
            v = 8 - 2 * mm - tt - h
            if v < best:
                best = v
            return
        r = i % 9
        if c[i] >= 3:
            c[i] -= 3
            dfs(i, m + 1, t, h)
            c[i] += 3
        if i < 27 and r <= 6 and c[i + 1] and c[i + 2]:
            c[i] -= 1; c[i + 1] -= 1; c[i + 2] -= 1
            dfs(i, m + 1, t, h)
            c[i] += 1; c[i + 1] += 1; c[i + 2] += 1
        if c[i] >= 2 and not h:
            c[i] -= 2
            dfs(i, m, t, 1)
            c[i] += 2
        if c[i] >= 2:
            c[i] -= 2
            dfs(i, m, t + 1, h)
            c[i] += 2
        if i < 27:
            if r <= 7 and c[i + 1]:
                c[i] -= 1; c[i + 1] -= 1
                dfs(i, m, t + 1, h)
                c[i] += 1; c[i + 1] += 1
            if r <= 6 and c[i + 2]:
                c[i] -= 1; c[i + 2] -= 1
                dfs(i, m, t + 1, h)
                c[i] += 1; c[i + 2] += 1
        c[i] -= 1
        dfs(i, m, t, h)
        c[i] += 1

    dfs(0, 0, 0, 0)
    return best


_SH_CACHE = {}


def shanten(tiles, melds=0):
    # 单视角牌谱里别人的暗牌是 '?'，tile_index 返回 -1，必须剔掉，
    # 否则 c[-1] 会把最后一张牌算多，4 副露的对手被误判成听牌。
    key = (tuple(sorted(i for i in (tile_index(t) for t in tiles) if i >= 0)), melds)
    v = _SH_CACHE.get(key)
    if v is not None:
        return v
    c = [0] * 34
    for i in key[0]:
        c[i] += 1
    best = _shanten_std(c[:], melds)
    if melds == 0:
        pairs = sum(1 for x in c if x >= 2)
        kinds = sum(1 for x in c if x >= 1)
        best = min(best, 6 - pairs + max(0, 7 - kinds))
        yao = (0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33)
        k = sum(1 for i in yao if c[i])
        best = min(best, 13 - k - (1 if any(c[i] >= 2 for i in yao) else 0))
    if len(_SH_CACHE) > 200000:      # 缓存无上限会让批量复盘把内存吃光
        _SH_CACHE.clear()
    _SH_CACHE[key] = best
    return best


def waiting_tiles(tiles, melds=0, kawa=()):
    cnt = Counter(tile_index(t) for t in tiles)
    out = set()
    for i in range(34):
        if cnt[i] >= 4:
            continue  # 手里已经四张，第 5 张是虚听
        if shanten(list(tiles) + [tile_name(i)], melds) == -1:
            out.add(i)
    # 舍张振听：任意一张待牌在自己牌河里，整手牌都不能荣和
    if out & set(kawa):
        return set()
    return out


class State:
    __slots__ = ('ordinal', 'bakaze', 'kyoku', 'honba', 'oya', 'scores',
                 'dora_markers', 'tehai', 'kawa', 'melds', 'riichi',
                 'riichi_junme', 'riichi_seq', 'junme', 'n_kan')

    def snapshot(self):
        return {
            'ordinal': self.ordinal, 'bakaze': self.bakaze, 'kyoku': self.kyoku,
            'honba': self.honba, 'oya': self.oya, 'scores': list(self.scores),
            'dora_markers': list(self.dora_markers),
            'tehai': [list(t) for t in self.tehai],
            'kawa': [[dict(d) for d in k] for k in self.kawa],
            'melds': [[dict(m) for m in p] for p in self.melds],
            'riichi': list(self.riichi),
            'riichi_junme': list(self.riichi_junme),
            'riichi_seq': list(self.riichi_seq),
            'junme': [x + 1 for x in self.junme],
            'n_kan': self.n_kan,
        }


def _can_call(snap, target, actor, discard):
    if actor == target or snap['riichi'][target] or len(snap['melds'][target]) >= 4:
        return False
    hand = Counter(tile_index(t) for t in snap['tehai'][target])
    d = tile_index(discard)
    if hand[d] >= 2:
        return True
    suit, n = parse_tile(discard)
    if suit != 'z' and (actor + 1) % 4 == target:
        for delta in (-2, -1, 1, 2):
            nn = n + delta
            if 1 <= nn <= 9:
                lo = min(n, nn)
                need = [tile_index(f'{x}{suit}') for x in range(lo, lo + 3) if x != n]
                if len(need) == 2 and all(hand[t] for t in need):
                    return True
    return False


def decisions(log, target):
    out = []
    st = None
    ordinal = -1
    post_call = False
    for idx, ev in enumerate(log):
        typ = ev['type']
        if typ == 'start_kyoku':
            ordinal += 1
            st = State()
            st.ordinal = ordinal
            st.bakaze, st.kyoku, st.honba, st.oya = ev['bakaze'], ev['kyoku'], ev['honba'], ev['oya']
            st.scores = list(ev['scores'])
            st.dora_markers = [ev['dora_marker']]
            st.tehai = [list(t) for t in ev['tehais']]
            st.kawa = [[] for _ in range(4)]
            st.melds = [[] for _ in range(4)]
            st.riichi = [False] * 4
            st.riichi_junme = [None] * 4
            st.riichi_seq = [None] * 4
            st.junme = [0] * 4
            st.n_kan = 0
            continue
        if st is None:
            continue
        if typ == 'tsumo':
            a = ev['actor']
            st.tehai[a].append(ev['pai'])
            if a == target and not st.riichi[a]:
                out.append(('tsumo', idx, st.snapshot(), ev['pai'], a))
        elif typ == 'dahai':
            a, pai = ev['actor'], ev['pai']
            # 鸣牌后、切牌前的那一手：Mortal 的 state.tehai 是切牌前的 11/8/5 张，
            # 所以快照要在改手牌/牌河/巡目之前拍，否则精确匹配 100% 失败。
            if a == target and post_call:
                out.append(('post_call', idx, st.snapshot(), pai, a))
            if pai in st.tehai[a]:
                st.tehai[a].remove(pai)
            st.kawa[a].append({'pai': pai, 'tsumogiri': ev.get('tsumogiri', False),
                               'riichi': st.riichi[a], 'junme': st.junme[a] + 1,
                               'seq': idx, 'actor': a})
            st.junme[a] += 1
            if a != target and _can_call(st.snapshot(), target, a, pai):
                out.append(('call', idx, st.snapshot(), pai, a))
            post_call = False
        elif typ in ('chi', 'pon', 'daiminkan'):
            a = ev['actor']
            for c in ev.get('consumed', []):
                if c in st.tehai[a]:
                    st.tehai[a].remove(c)
            st.melds[a].append({'type': typ, 'pai': ev['pai'],
                                'consumed': list(ev.get('consumed', [])), 'from': ev.get('target')})
            src = ev.get('target')
            if src is not None and st.kawa[src]:
                # 被鸣走的牌仍然是打牌者的舍牌（现物、舍张振听的依据），不能删；
                # 只标 called，visible() 统计可见枚数时跳过它（已经算在副露里了）。
                d = st.kawa[src][-1]
                if d['pai'] == ev['pai'] or tile_index(d['pai']) == tile_index(ev['pai']):
                    d['called'] = True
                else:
                    st.kawa[src].pop()
            # 吃/碰之后立刻切牌，要 post_call 点；大明杠之后先摸岭上牌，由 tsumo 点覆盖
            if a == target and typ != 'daiminkan':
                post_call = True
        elif typ in ('ankan', 'kakan'):
            a = ev['actor']
            for c in ev.get('consumed', []):
                if c in st.tehai[a]:
                    st.tehai[a].remove(c)
            if typ == 'kakan':
                # 加杠：pai 是手牌里的第 4 张（必须先删掉），consumed 是原来碰的 3 张
                # （已经在 meld 里了，不能再追加，否则可见牌会变成 6 张）
                if ev['pai'] in st.tehai[a]:
                    st.tehai[a].remove(ev['pai'])
                for m in st.melds[a]:
                    if m['type'] == 'pon' and tile_index(m['pai']) == tile_index(ev['pai']):
                        m['type'] = 'kakan'
                        m['consumed'] = list(m['consumed']) + [ev['pai']]
                        break
                else:
                    st.melds[a].append({'type': typ, 'pai': ev['pai'],
                                        'consumed': list(ev.get('consumed', [])) + [ev['pai']],
                                        'from': a})
            else:
                # 暗杠事件没有 pai 字段（mjai 标准），用 consumed[0] 占位；
                # visible() 里按 consumed 计数，不会重复
                cons = list(ev.get('consumed', []))
                st.melds[a].append({'type': typ, 'pai': ev.get('pai') or (cons[0] if cons else None),
                                    'consumed': cons, 'from': a})
            st.n_kan += 1
        elif typ == 'hora':
            # 和了/见逃也是一次决策：和了就地和，见逃则接着打。
            # 快照就是「和了那一刻」的手牌（自摸 14 张、荣和 13 张）
            if ev.get('actor') == target:
                out.append(('hora', idx, st.snapshot(), ev.get('pai'), ev.get('actor')))
        elif typ == 'reach':
            a = ev['actor']
            st.riichi[a] = True
            st.riichi_junme[a] = st.junme[a]
            st.riichi_seq[a] = idx
        elif typ == 'dora':
            st.dora_markers.append(ev['dora_marker'])
        elif typ == 'end_kyoku':
            st = None
    return out


def act_key(a, plain=False):
    """动作转可比较的键。

    plain=True 是「宽松键」：忽略摸切/手切、赤五、副露顺序。
    Mortal 的 37 维动作空间里同一种牌只有一条候选（不分摸切/手切），
    红五也可能被固定成打红五，所以精确键查不到时必须再试宽松键。
    """
    t = a.get('type')

    def norm(x):
        return str(x or '').replace('r', '') if plain else x

    if t == 'dahai':
        if plain:
            return ('dahai', norm(a.get('pai')))
        return ('dahai', a.get('pai'), bool(a.get('tsumogiri')))
    if t == 'none':
        return ('none',)
    if plain:
        return (t, norm(a.get('pai')), tuple(sorted(norm(x) for x in (a.get('consumed') or ()))))
    return (t, a.get('pai'), tuple(a.get('consumed') or ()))


def _pick_q(exact, relaxed, act, details, idx=None):
    """取一个动作的 Q 值：精确键 → details[actual_index] → 宽松键。

    顺序很重要：宽松键会把赤五（5mr）和普通五（5m）归一成同一个键，
    手里同时有这两张时会把另一张的 Q 取过来。报告自带的 actual_index 是
    Mortal 自己算的，比任何模糊键都准，所以必须排在宽松键之前。
    """
    v = exact.get(act_key(act))
    if v is not None:
        return v
    if isinstance(idx, int) and 0 <= idx < len(details):
        return details[idx]['q_value']
    w = relaxed.get(act_key(act, True))
    if w is not None:
        return w
    return None


def _align_kyoku(entries, points, target):
    n, m = len(entries), len(points)
    NEG = -1e9

    def ms(tiles):
        return tuple(sorted(tile_index(t) for t in tiles))

    match = [None] * n
    used = [False] * m
    cur = 0
    for i, e in enumerate(entries):
        want = ms(e['state']['tehai'])
        hit = -1
        for j in range(cur, m):
            if not used[j] and ms(points[j][2]['tehai'][target]) == want:
                hit = j
                break
        if hit >= 0:
            match[i] = points[hit]
            used[hit] = True
            cur = hit + 1
            continue
        # Mortal 把立直拆成「要不要立直」和「立直切哪张」两条 entry，
        # 两条的 state.tehai 是同一副 14 张牌，只能共用同一个快照。
        # 只对 at_self_riichi 这种 entry 放行；别的 entry 复用会掩盖真正的错位。
        if e.get('at_self_riichi'):
            for j in range(max(0, cur - 4), m):
                if used[j] and ms(points[j][2]['tehai'][target]) == want:
                    match[i] = points[j]
                    break
    rest_e = [i for i in range(n) if match[i] is None]
    rest_p = [j for j in range(m) if not used[j]]
    if rest_e and rest_p:
        def score(e, p):
            s = 0.0
            if e.get('tile') == p[3]:
                s += 3
            if e.get('last_actor') == p[4]:
                s += 2
            s += 2 if e.get('junme') == p[2]['junme'][target] else 0
            return s if s > 0 else -1.0
        ne, np_ = len(rest_e), len(rest_p)
        dp = [[NEG] * (np_ + 1) for _ in range(ne + 1)]
        bt = [[None] * (np_ + 1) for _ in range(ne + 1)]
        dp[0][0] = 0
        for i in range(ne + 1):
            for j in range(np_ + 1):
                cur_v = dp[i][j]
                if cur_v == NEG:
                    continue
                if i < ne and j < np_:
                    v = cur_v + score(entries[rest_e[i]], points[rest_p[j]])
                    if v > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = v
                        bt[i + 1][j + 1] = ('m', i, j)
                if i < ne and cur_v - 0.6 > dp[i + 1][j]:
                    dp[i + 1][j] = cur_v - 0.6
                    bt[i + 1][j] = ('e', i, None)
                if j < np_ and cur_v - 0.6 > dp[i][j + 1]:
                    dp[i][j + 1] = cur_v - 0.6
                    bt[i][j + 1] = ('p', None, j)
        i, j = ne, np_
        while i > 0 or j > 0:
            b = bt[i][j]
            if b is None:
                break
            if b[0] == 'm':
                match[rest_e[b[1]]] = points[rest_p[b[2]]]
                i, j = i - 1, j - 1
            elif b[0] == 'e':
                i -= 1
            else:
                j -= 1
    return match


CALL_TYPES = {'chi', 'pon', 'daiminkan', 'ankan', 'kakan', 'none'}
CATS = ('牌效', '防守', '副露压力下', '立直判断', '鸣牌判断', '和了', '未知')


def classify(entry, snap, target):
    # 和了/见逃不是牌效决策，单独一类：它已经由和了率、放铳率反映过了。
    # 判 details 而不是 actual：见逃时 actual 是打牌，只看 actual 会把它算进牌效。
    types = {act_key(x['action'])[0] for x in entry['details']}
    if 'hora' in types or (entry.get('actual') or {}).get('type') == 'hora':
        return '和了'
    if 'reach' in types:
        return '立直判断'
    if types and types <= CALL_TYPES:
        return '鸣牌判断'
    if snap is None:
        return '未知'
    if any(snap['riichi'][p] for p in range(4) if p != target):
        return '防守'
    if any(len([m for m in snap['melds'][p] if m['type'] != 'ankan']) >= 2
           for p in range(4) if p != target):
        return '副露压力下'
    return '牌效'


def verify_report(report):
    """报告结构校验：缺字段、三麻都给出人看得懂的报错，而不是 KeyError/IndexError。"""
    if not isinstance(report, dict):
        raise ValueError('报告为空或格式不对')
    log = report.get('mjai_log')
    if not isinstance(log, list) or not log:
        raise ValueError('报告里没有 mjai_log，可能下载不完整')
    if not isinstance(report.get('review', {}).get('kyokus'), list):
        raise ValueError('报告里没有 review.kyokus')
    if not isinstance(report.get('player_id'), int):
        raise ValueError('报告缺少 player_id')
    start = next((e for e in log if e.get('type') == 'start_kyoku'), None)
    if start is None:
        raise ValueError('报告里没有 start_kyoku')
    n = len(start.get('tehais') or [])
    if n != 4:
        raise ValueError(f'这场是 {n} 人麻将，当前版本只支持四麻')
    return True


def analyze(report):
    verify_report(report)
    target = report['player_id']
    pts = decisions(report['mjai_log'], target)
    by_ky = {}
    for p in pts:
        by_ky.setdefault(p[2]['ordinal'], []).append(p)
    rows = []
    for kn, ky in enumerate(report['review']['kyokus']):
        entries = ky['entries']
        plist = by_ky.get(kn, [])
        match = _align_kyoku(entries, plist, target)
        for i, e in enumerate(entries):
            snap = match[i][2] if match[i] else None
            details = e.get('details') or []
            if not details:
                continue
            exact, relaxed = {}, {}
            for x in details:
                exact.setdefault(act_key(x['action']), x['q_value'])
                relaxed.setdefault(act_key(x['action'], True), x['q_value'])
            q_exp = _pick_q(exact, relaxed, e['expected'], details, 0)
            q_act = _pick_q(exact, relaxed, e['actual'], details, e.get('actual_index'))
            if q_act is None or q_exp is None:
                continue
            rows.append({
                'kyoku': kn, 'junme': e['junme'], 'tile': e['tile'],
                'cat': classify(e, snap, target), 'diff': q_exp - q_act,
                'q_actual': q_act, 'q_expected': q_exp,
                'actual': e['actual'], 'expected': e['expected'],
                'snap': snap, 'entry': e, 'matched': match[i] is not None,
            })
    return rows


def summary(rows):
    n = len(rows)
    s = {'n': n}
    for cat in CATS:
        sub = [r for r in rows if r['cat'] == cat]
        s[cat] = sum(r['diff'] for r in sub) / n * 100 if n else 0.0
        s[cat + '_n'] = len(sub)
        s[cat + '_raw'] = sum(r['diff'] for r in sub)
    s['loss'] = sum(r['diff'] for r in rows) / n * 100 if n else 0.0
    s['severe'] = sum(1 for r in rows if r['diff'] >= 1.0) / n * 100 if n else 0.0
    return s


LADDER = {0: '现物', 1: '见3字牌', 2: '见2字牌·筋1·9', 3: '生张字牌·筋2-8',
          4: '无筋1·2·8·9', 5: '无筋中张3-7'}


def visible(snap, me=None):
    c = Counter()
    if me is not None:
        for t in snap['tehai'][me]:
            c[tile_index(t)] += 1
    for p in range(4):
        for d in snap['kawa'][p]:
            # 被吃碰走的舍牌已经算在副露里了，别重复计
            if d.get('called'):
                continue
            c[tile_index(d['pai'])] += 1
        for m in snap['melds'][p]:
            if m['type'] == 'ankan':
                # 暗杠没有 pai 字段，四张都在 consumed 里
                for t in m['consumed']:
                    c[tile_index(t)] += 1
                continue
            if m.get('pai'):
                c[tile_index(m['pai'])] += 1
            for t in m['consumed']:
                c[tile_index(t)] += 1
    for dm in snap['dora_markers']:
        c[tile_index(dm)] += 1
    return c


def is_genbutsu(snap, opp, t):
    for d in snap['kawa'][opp]:
        if tile_index(d['pai']) == t:
            return True
    rs = snap['riichi_seq'][opp]
    if rs is not None:
        for p in range(4):
            if p == opp:
                continue
            for d in snap['kawa'][p]:
                if d['seq'] > rs and tile_index(d['pai']) == t:
                    return True
    return False


def safety(snap, opp, t, vis=None):
    if is_genbutsu(snap, opp, t):
        return 0
    if vis is None:
        vis = visible(snap)
    s, n = parse_tile(tile_name(t))
    if s == 'z':
        seen = vis.get(t, 0)
        return 1 if seen >= 3 else (2 if seen == 2 else 3)
    sides = [n + d for d in (-3, 3) if 1 <= n + d <= 9]
    hit = [nn for nn in sides if is_genbutsu(snap, opp, tile_index(f'{nn}{s}'))]
    if hit and len(hit) == len(sides):
        return 2 if n in (1, 9) else 3
    return 4 if n in (1, 2, 8, 9) else 5


def worst_safety(snap, target, t):
    opps = [p for p in range(4) if snap['riichi'][p] and p != target]
    if not opps:
        return None, ''
    vis = visible(snap, target)
    g = max(safety(snap, p, t, vis) for p in opps)
    return g, LADDER[g]


def pressure(rows, target):
    bucket = {k: [0, 0.0, 0, 0, 0.0] for k in ('none', 'hidden', 'riichi')}
    for r in rows:
        if r['actual'].get('type') != 'dahai' or not r['snap']:
            continue
        snap = r['snap']
        riichi = any(snap['riichi'][p] for p in range(4) if p != target)
        tenpai, wait_all = False, set()
        for p in range(4):
            if p == target:
                continue
            if shanten(snap['tehai'][p], len(snap['melds'][p])) == 0:
                tenpai = True
                kawa = {tile_index(x['pai']) for x in snap['kawa'][p]}
                wait_all |= waiting_tiles(snap['tehai'][p], len(snap['melds'][p]), kawa)
        key = 'riichi' if riichi else ('hidden' if tenpai else 'none')
        b = bucket[key]
        b[0] += 1
        b[1] += r['diff']
        b[4] += r['diff'] ** 2
        if tile_index(r['actual']['pai']) in wait_all:
            b[2] += 1
        if r['expected'].get('type') == 'dahai' and tile_index(r['expected']['pai']) in wait_all:
            b[3] += 1
    out = {k: {'n': v[0], 'loss': v[1], 'sq': v[4], 'per100': (v[1] / v[0] * 100 if v[0] else 0.0),
               'deal': v[2], 'm_deal': v[3]} for k, v in bucket.items()}
    n = out['riichi']['n'] + out['hidden']['n']
    loss = out['riichi']['loss'] + out['hidden']['loss']
    out['merged'] = {'n': n, 'loss': loss, 'sq': out['riichi']['sq'] + out['hidden']['sq'],
                     'per100': loss / n * 100 if n else 0.0}
    return out


def log_stats(report_or_log):
    """不需要 Mortal 的部分：局数、和了率、放铳率、立直率、副露率、平均打点。"""
    log = report_or_log['mjai_log'] if 'mjai_log' in report_or_log else report_or_log
    target = report_or_log.get('player_id', 0)
    kyo = win = deal = riichi = meld = meld_kyo = 0
    win_pt = deal_pt = 0
    called = dealt = False
    for e in log:
        t = e['type']
        if t == 'start_kyoku':
            kyo += 1
            called = dealt = False
        elif t == 'hora':
            if e['actor'] == target:
                win += 1
                win_pt += e['deltas'][target]
            elif e['target'] == target:
                # 双响：一炮两家，放铳局数只算 1，铳点两家相加
                deal_pt -= e['deltas'][target]
                if not dealt:
                    dealt = True
                    deal += 1
        elif t == 'reach' and e['actor'] == target:
            riichi += 1
        elif t in ('chi', 'pon', 'daiminkan', 'ankan', 'kakan') and e['actor'] == target:
            meld += 1
            if not called:
                called = True
                meld_kyo += 1
    return {
        'kyoku': kyo, 'win': win, 'deal': deal, 'riichi': riichi,
        'meld': meld, 'meld_kyo': meld_kyo,
        'win_rate': win / kyo * 100 if kyo else 0,
        'deal_rate': deal / kyo * 100 if kyo else 0,
        'riichi_rate': riichi / kyo * 100 if kyo else 0,
        'meld_rate': meld_kyo / kyo * 100 if kyo else 0,
        'avg_win': win_pt / win if win else 0,
        'avg_deal': deal_pt / deal if deal else 0,
    }


def final_scores(report):
    scores, oya = [25000] * 4, 0
    kyotaku = 0  # 供托：桌上还没人拿走的立直棒
    for e in report['mjai_log']:
        if e['type'] == 'start_kyoku':
            scores, oya = list(e['scores']), e['oya']
            # 起局时桌上剩几根立直棒是权威值，直接同步，别和下面的计数叠加
            kyotaku = int(e.get('kyotaku') or 0)
        elif e['type'] == 'end_game' and e.get('scores'):
            scores = list(e['scores'])
        elif e['type'] in ('hora', 'ryukyoku', 'ryuukyoku', 'reach_accepted'):
            if e.get('scores'):
                scores = list(e['scores'])
            elif e['type'] == 'reach_accepted':
                scores[e['actor']] -= 1000
                kyotaku += 1
            else:
                for i, d in enumerate(e.get('deltas') or []):
                    scores[i] += d
                # 和了时桌上的立直棒进了和牌者收入；流局时留在桌上继续累积
                if e['type'] == 'hora':
                    kyotaku = 0
    # 终局还在桌上的供托按天凤/雀魂规则归头名；不补这一步终局总分不会是 100000
    if kyotaku > 0:
        top = max(range(4), key=lambda i: (scores[i], -i))
        scores[top] += kyotaku * 1000
    # 天凤/雀魂终局同分：按起家座次 0→1→2→3 定顺位，与末局庄家无关
    order = sorted(range(4), key=lambda p: (-scores[p], p))
    return scores[report['player_id']], order.index(report['player_id']) + 1


def _download_report(rid, path):
    """下载到临时文件再 os.replace，避免半截文件；解析不了就删掉重来。"""
    url = f'https://mjai.ekyu.moe/report/{rid}.json'
    raw = _urlopen(url)
    tmp = path + '.part'
    with open(tmp, 'wb') as f:
        f.write(raw)
    os.replace(tmp, path)


def load_report(rid):
    # rid 直接拼进文件名，必须只允许 16 位十六进制，否则 '../..' 能写到缓存目录外面
    rid = str(rid or '').strip().lower()
    if not re.fullmatch(r'[0-9a-f]{16}', rid):
        raise ValueError(f'报告 id 不合法：{rid!r}')
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'{rid}.json')
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            os.remove(path)          # 坏缓存（错误页/截断），删了重下
    _download_report(rid, path)
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def act_cn(a):
    t = a.get('type')
    if t == 'dahai':
        return ('摸切' if a.get('tsumogiri') else '') + a.get('pai', '')
    if t == 'none':
        return '过'
    return {'reach': '立直', 'chi': '吃', 'pon': '碰', 'daiminkan': '大明杠',
            'ankan': '暗杠', 'kakan': '加杠', 'hora': '和了'}.get(t, str(t))


def kyoku_name(snap):
    if not snap:
        return '?'
    names = {'E': '东', 'S': '南', 'W': '西', 'N': '北'}
    return f"{names.get(snap['bakaze'], snap['bakaze'])}{snap['kyoku']}" + (
        f' {snap["honba"]}本' if snap['honba'] else '')


def report_one(rid, top=0, want_pr=True):
    d = load_report(rid)
    target = d['player_id']
    rows = analyze(d)
    s = summary(rows)
    score, rank = final_scores(d)
    ls = log_stats(d)
    pr = pressure(rows, target) if want_pr else None
    prtxt = ('%.1f（%d 次）' % (pr['merged']['per100'], pr['merged']['n'])) if pr else '—'
    out = [f"== {rid}  第{rank}位 {score}  R{d['review']['rating'] * 100:.1f}  N{s['n']}",
           "5项: 合计%.2f | 每100次牌效决策 %.1f（%d 次） | 每100次防守决策 %s | 压力分数 %s | 每100手严重失误 %.2f（%d 次）"
           % (s['loss'],
              s['牌效_raw'] / s['牌效_n'] * 100 if s['牌效_n'] else 0, s['牌效_n'],
              ('%.1f（%d 次）' % (s['防守_raw'] / s['防守_n'] * 100, s['防守_n'])) if s['防守_n'] else '—',
              prtxt, s['severe'], round(s['severe'] * s['n'] / 100)),
           "辅: 牌效%.2f 防守%.2f 副露压力下%.2f 立直%.2f 鸣牌%.2f | 和了%.1f%% 放铳%.1f%% 立直%.1f%% 副露%.1f%%"
           % (s['牌效'], s['防守'], s['副露压力下'], s['立直判断'], s['鸣牌判断'],
              ls['win_rate'], ls['deal_rate'], ls['riichi_rate'], ls['meld_rate'])]
    if pr:
        out.append('压力: 立直威胁 %.1f（%d 次，失分 %.3f，sq %.3f） 隐形威胁 %.1f（%d 次，失分 %.3f，sq %.3f） 无威胁 %.1f（%d 次）'
                   % (pr['riichi']['per100'], pr['riichi']['n'], pr['riichi']['loss'], pr['riichi']['sq'],
                      pr['hidden']['per100'], pr['hidden']['n'], pr['hidden']['loss'], pr['hidden']['sq'],
                      pr['none']['per100'], pr['none']['n']))
    if top:
        out.append(f'Q 差前 {top} 手：')
        for r in sorted(rows, key=lambda x: -x['diff'])[:top]:
            hand = ' '.join(sorted(r['entry']['state']['tehai'], key=tile_index))
            out.append('  [%s] %s %d巡  你 %s %.2f → Mortal %s %.2f  差 %.2f'
                       % (r['cat'], kyoku_name(r['snap']), r['junme'],
                          act_cn(r['actual']), r['q_actual'],
                          act_cn(r['expected']), r['q_expected'], r['diff']))
            extra = ''
            if r['cat'] == '防守' and r['snap']:
                g1, l1 = worst_safety(r['snap'], target, tile_index(r['actual']['pai']))
                g2, l2 = worst_safety(r['snap'], target, tile_index(r['expected']['pai'])) \
                    if r['expected'].get('type') == 'dahai' else (None, '')
                extra = ' | 安全度 你的 %s / Mortal %s' % (l1 or '—', l2 or '—')
            out.append(f'        手牌 {hand}（向听 {shanten(r["entry"]["state"]["tehai"], len(r["entry"]["state"].get("fuuros") or []))}）{extra}')
    return '\n'.join(out)


def table_row(rid, no=0):
    d = load_report(rid)
    rows = analyze(d)
    s = summary(rows)
    score, rank = final_scores(d)
    # 没有防守样本时写「—」而不是 0：0 会被读成「防守满分」，和 build_row 的 '' 也统一。
    dfn = f'{s["防守_raw"] / s["防守_n"] * 100:.1f}' if s['防守_n'] else '—'
    return f'| {no or "?"} | 日期 | | ' + '%d | %.1f | %d | %.2f | %.2f | %.2f | %d / %s | %.2f | %.2f | %.2f | %.2f | %d |' % (
        rank, d['review']['rating'] * 100, s['n'], s['loss'], s['牌效'], s['防守'],
        s['防守_n'], dfn,
        s['severe'], s['副露压力下'], s['立直判断'], s['鸣牌判断'], s['牌效_n'])


XLSX_SHEET = '逐场'

_FILE_ATTRIBUTE_READONLY = 0x1


def is_readonly(path):
    """文件是不是被设成只读（我们用来防人手改）。"""
    if not os.path.exists(path):
        return False
    if os.name == 'nt':
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs in (0xFFFFFFFF, -1):
            return False
        return bool(attrs & _FILE_ATTRIBUTE_READONLY)
    return not os.access(path, os.W_OK)


def set_readonly(path, on):
    """只读开关：Windows 改文件属性，macOS/Linux 改 chmod。成功返回 True。"""
    if not os.path.exists(path):
        return False
    try:
        if os.name == 'nt':
            import ctypes
            k32 = ctypes.windll.kernel32
            attrs = k32.GetFileAttributesW(str(path))
            if attrs in (0xFFFFFFFF, -1):
                return False
            new = (attrs | _FILE_ATTRIBUTE_READONLY) if on else (attrs & ~_FILE_ATTRIBUTE_READONLY)
            return bool(k32.SetFileAttributesW(str(path), new))
        mode = os.stat(path).st_mode
        os.chmod(path, (mode & ~0o222) if on else (mode | 0o200))
        return True
    except Exception:
        return False


# 报告里嵌着原始天凤牌谱的头信息（split_logs[0].rule.disp），头一个字就是卓
LOBBY_NAMES = {'般': '一般', '上': '上级', '特': '特上', '鳳': '凤凰', '凤': '凤凰', '雀': '雀魂'}


def report_meta(report):
    """从报告里挖出卓、同桌玩家名。报告里的 split_logs[0] 就是原始天凤牌谱，rule.disp 例如「上南喰赤」。"""
    out = {'lobby': '', 'players': []}
    for blk in (report.get('split_logs') or []):
        if not isinstance(blk, dict):
            continue
        disp = str((blk.get('rule') or {}).get('disp') or '')
        if disp:
            out['lobby'] = LOBBY_NAMES.get(disp[0], '')
        names = blk.get('name') or []
        if names:
            out['players'] = [str(x) for x in names]
        break
    return out


def now_stamp():
    """没给牌谱链接时，用当前时间当日期，格式统一 YYYY-MM-DD HH时。"""
    import datetime
    t = datetime.datetime.now()
    return f'{t.year}-{t.month:02d}-{t.day:02d} {t.hour:02d}时'


def tenhou_info(link):
    """从天凤链接或牌谱编号里取出 log id、座位、时间、卓。"""
    if not link:
        return None, None, '', ''
    q = re.search(r'paipu=([0-9a-zA-Z_-]+)', link)
    if q and not re.search(r'\d{10}gm-', link):
        tok = q.group(1)
        # 雀魂的 paipu 有两种：251125-xxxx-… 和混淆过的 jmjnt-…
        m6 = re.match(r'(\d{6})', tok)
        when = f'20{m6.group(1)[0:2]}-{m6.group(1)[2:4]}-{m6.group(1)[4:6]}' if m6 else ''
        return tok, None, when, '雀魂'
    m = re.search(r'(\d{10}gm-([0-9a-f]{4})-\d{4}-[0-9a-f]{8})', link)
    log = m.group(1) if m else None
    tw = re.search(r'tw=(\d)', link)
    when = f'{log[0:4]}-{log[4:6]}-{log[6:8]} {log[8:10]}时' if log else ''
    # 天凤房间号：末位 9=四麻、1=三麻东风；前两位区分一般/上级/特上/凤凰
    _ROOM = {'0': '一般', '8': '上级', 'a': '特上', 'e': '凤凰'}
    lobby = ''
    if m:
        lobby = _ROOM.get(m.group(2)[2:3], m.group(2))
        if m.group(2)[3:4] == '1':
            lobby += '东风'
    return log, (int(tw.group(1)) if tw else None), when, lobby


XLSX_HEAD = ['序号', '日期', '卓', '状态', '顺位', '终局点数', 'rating', '决策', '合计失分', '牌效', '防守',
             '防守决策次数', '每100次防守决策', '严重失误', '副露压力下', '立直', '鸣牌', '牌效决策次数',
             '每100次牌效决策', '立直威胁次数', '立直威胁失分', '立直威胁sq', '隐形威胁次数', '隐形威胁失分',
             '隐形威胁sq', '压力分数(合并)', '和了率%', '放铳率%', '天凤牌谱', 'tw', '报告ID', '口径', '备注']


def new_workbook(path):
    """建一份空白数据表：逐场（只有表头）、汇总（按卓分列的公式）、说明。"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = XLSX_SHEET
    ws.append(XLSX_HEAD)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill('solid', fgColor='DDEBF7')
    ws.freeze_panes = 'B2'
    for i, h in enumerate(XLSX_HEAD, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(8, min(30, len(h) * 2 + 2))
    L = lambda h: get_column_letter(XLSX_HEAD.index(h) + 1)
    R = lambda h: f'{XLSX_SHEET}!{L(h)}2:{L(h)}3000'
    s = wb.create_sheet('汇总')
    groups = ['全部', '一般', '上级', '特上', '凤凰', '雀魂']
    s.append(['项目（公式，随逐场表自动更新）'] + groups)
    def mask(g):
        return f'({R("序号")}<>"")' if g == '全部' else f'({R("卓")}="{g}")'
    def wavg(g, val, w):
        return f'=IFERROR(SUMPRODUCT({mask(g)}*{R(w)}*{R(val)})/SUMPRODUCT({mask(g)}*{R(w)}),"")'
    items = [
        ('场数', lambda g: f'=SUMPRODUCT({mask(g)}*1)'),
        ('平均顺位', lambda g: f'=IFERROR(SUMPRODUCT({mask(g)}*{R("顺位")})/SUMPRODUCT({mask(g)}*1),"")'),
        ('4 位率', lambda g: f'=IFERROR(SUMPRODUCT({mask(g)}*({R("顺位")}=4))/SUMPRODUCT({mask(g)}*1),"")'),
        ('平均 rating', lambda g: f'=IFERROR(SUMPRODUCT({mask(g)}*{R("rating")})/SUMPRODUCT({mask(g)}*1),"")'),
        ('合计失分（按决策加权）', lambda g: wavg(g, '合计失分', '决策')),
        ('每100次牌效决策', lambda g: f'=IFERROR(SUMPRODUCT({mask(g)}*{R("决策")}*{R("牌效")})/SUMPRODUCT({mask(g)}*{R("牌效决策次数")}),"")'),
        ('每100次防守决策', lambda g: wavg(g, '每100次防守决策', '防守决策次数')),
        ('严重失误（每100手）', lambda g: wavg(g, '严重失误', '决策')),
        ('压力分数', lambda g: f'=IFERROR(SUMPRODUCT({mask(g)}*({R("立直威胁失分")}+{R("隐形威胁失分")}))'
                                f'/SUMPRODUCT({mask(g)}*({R("立直威胁次数")}+{R("隐形威胁次数")}))*100,"")'),
        ('和了率%', lambda g: f'=IFERROR(SUMPRODUCT({mask(g)}*{R("和了率%")})/SUMPRODUCT({mask(g)}*1),"")'),
        ('放铳率%', lambda g: f'=IFERROR(SUMPRODUCT({mask(g)}*{R("放铳率%")})/SUMPRODUCT({mask(g)}*1),"")'),
    ]
    for name, f in items:
        s.append([name] + [f(g) for g in groups])
    for c in s[1]:
        c.font = Font(bold=True)
    s.column_dimensions['A'].width = 28
    for i in range(2, 8):
        s.column_dimensions[get_column_letter(i)].width = 10
        for row in s.iter_rows(min_row=3, min_col=i, max_col=i):
            for c in row:
                c.number_format = '0.00'
    t = wb.create_sheet('说明')
    for line in ['每场一行，由「麻将记录」程序追加到「逐场」末尾；已有的行不会被改动，同一个报告 id 不会重复写。',
                 '写入前请关掉 Excel。「汇总」是公式，按「卓」分列（天凤链接自动识别一般 / 上级 / 特上 / 凤凰，雀魂链接记为雀魂）。',
                 '合计失分 = 每 100 手和 Mortal 最优选择的 Q 值差之和；严重失误 = Q 差 ≥ 1.0 的手数（每 100 手）。',
                 '压力分数 = 有人立直、或没立直但已有人听牌时，每 100 次切牌的失分。']:
        t.append([line])
    t.column_dimensions['A'].width = 110
    wb.save(path)


def build_row(g, link='', note='', data_link=None, no=None):
    """由一次计算的结果拼出「逐场」表的一行（字典，键就是表头）。"""
    d, s, pr, ls = g['d'], g['s'], g['pr'], g['ls']
    log, tw, when, lobby = tenhou_info(link)
    meta = report_meta(d)
    if not lobby:
        lobby = meta['lobby']
    if not when:
        when = now_stamp()
    elif '时' not in when:
        when = when + ' 00时'
    return {
        '序号': no, '日期': when, '卓': lobby, '状态': '', '顺位': g['rank'],
        '终局点数': g['score'], 'rating': round(d['review']['rating'] * 100, 1),
        '决策': s['n'], '合计失分': round(s['loss'], 2), '牌效': round(s['牌效'], 2),
        '防守': round(s['防守'], 2), '防守决策次数': s['防守_n'],
        # 没有防守样本时留空，不要写 0——0 会被当成「完美防守」拉低汇总和区间筛选
        '每100次防守决策': round(s['防守_raw'] / s['防守_n'] * 100, 1) if s['防守_n'] else '',
        '严重失误': round(s['severe'], 2), '副露压力下': round(s['副露压力下'], 2),
        '立直': round(s['立直判断'], 2), '鸣牌': round(s['鸣牌判断'], 2),
        '牌效决策次数': s['牌效_n'],
        '每100次牌效决策': round(s['牌效_raw'] / s['牌效_n'] * 100, 1) if s['牌效_n'] else 0,
        '立直威胁次数': pr['riichi']['n'], '立直威胁失分': round(pr['riichi']['loss'], 3),
        '立直威胁sq': round(pr['riichi']['sq'], 3),
        '隐形威胁次数': pr['hidden']['n'], '隐形威胁失分': round(pr['hidden']['loss'], 3),
        '隐形威胁sq': round(pr['hidden']['sq'], 3),
        '压力分数(合并)': round(pr['merged']['per100'], 1) if pr['merged']['n'] else '',
        '和了率%': round(ls['win_rate'], 1), '放铳率%': round(ls['deal_rate'], 1),
        '天凤牌谱': log or '', 'tw': tw if tw is not None else '', '报告ID': g['rid'],
        '口径': 'mr.py', '备注': note,
    }


def append_xlsx(rid, path, link='', note='', state=None, data_link=None):
    """追加一行；返回 (行序号, 是否原本就有)。data_link 是数据文件的相对路径，会写成超链接。

    没给牌谱链接时，卓从报告里识别（rule.disp），日期用当前时间——只贴报告 id 也能记完整。
    """
    try:
        import openpyxl
    except ImportError:
        print('缺少 openpyxl：先在命令行运行  pip install openpyxl')
        return None, False
    if not os.path.exists(path):
        new_workbook(path)
        print(f'没找到数据表，已新建：{path}')
    wb = openpyxl.load_workbook(path)
    ws = wb[XLSX_SHEET]
    head = [c.value for c in ws[1]]
    col = {h: i for i, h in enumerate(head)}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[col['报告ID']] == rid:
            print(f'报告 {rid} 已经在第 {row[col["序号"]]} 行，没有重复写入')
            return row[col['序号']], True
    nos = [r[col['序号']] for r in ws.iter_rows(min_row=2, values_only=True) if isinstance(r[col['序号']], int)]
    no = (max(nos) if nos else 0) + 1
    d = load_report(rid)
    target = d['player_id']
    rows = analyze(d)
    s = summary(rows)
    score, rank = final_scores(d)
    ls = log_stats(d)
    pr = pressure(rows, target)
    log, tw, when, lobby = tenhou_info(link)
    meta = report_meta(d)
    if not lobby:
        lobby = meta['lobby']
    if not when:
        when = now_stamp()
    elif '时' not in when:
        when = when + ' 00时'
    val = {
        '序号': no, '日期': when, '卓': lobby, '状态': state or '', '顺位': rank, '终局点数': score,
        'rating': round(d['review']['rating'] * 100, 1), '决策': s['n'],
        '合计失分': round(s['loss'], 2), '牌效': round(s['牌效'], 2), '防守': round(s['防守'], 2),
        '防守决策次数': s['防守_n'],
        '每100次防守决策': round(s['防守_raw'] / s['防守_n'] * 100, 1) if s['防守_n'] else 0,
        '严重失误': round(s['severe'], 2), '副露压力下': round(s['副露压力下'], 2),
        '立直': round(s['立直判断'], 2), '鸣牌': round(s['鸣牌判断'], 2), '牌效决策次数': s['牌效_n'],
        '每100次牌效决策': round(s['牌效_raw'] / s['牌效_n'] * 100, 1) if s['牌效_n'] else 0,
        '立直威胁次数': pr['riichi']['n'], '立直威胁失分': round(pr['riichi']['loss'], 3),
        '立直威胁sq': round(pr['riichi']['sq'], 3),
        '隐形威胁次数': pr['hidden']['n'], '隐形威胁失分': round(pr['hidden']['loss'], 3),
        '隐形威胁sq': round(pr['hidden']['sq'], 3),
        '压力分数(合并)': round(pr['merged']['per100'], 1),
        '和了率%': round(ls['win_rate'], 1), '放铳率%': round(ls['deal_rate'], 1),
        '天凤牌谱': log or '', 'tw': tw if tw is not None else '', '报告ID': rid,
        '口径': 'mr.py', '备注': note,
    }
    ws.append([val.get(h, '') for h in head])
    if data_link:
        if '数据' not in head:
            ws.cell(row=1, column=len(head) + 1, value='数据')
            head.append('数据')
        cell = ws.cell(row=ws.max_row, column=head.index('数据') + 1, value='打开')
        cell.hyperlink = data_link
        cell.style = 'Hyperlink'
    # 表是「人只读」的：写之前临时解锁，写完立刻恢复原状，人手改不进去
    was_ro = is_readonly(path)
    if was_ro:
        set_readonly(path, False)
    try:
        try:
            wb.save(path)
        except PermissionError:
            print('写不进去：Excel 正开着这个文件。关掉 Excel 再运行一次。')
            return None, False
    finally:
        if was_ro:
            set_readonly(path, True)
    print(f'已追加第 {no} 行：{lobby or "?"} 第{rank}位 {score}  rating {val["rating"]}  '
          f'合计 {val["合计失分"]}  牌效决策 {val["每100次牌效决策"]}（{s["牌效_n"]} 次）  '
          f'防守决策 {val["每100次防守决策"]}（{s["防守_n"]} 次）  压力 {val["压力分数(合并)"]}  严重 {val["严重失误"]}')
    return no, False


def main():
    args = sys.argv[1:]
    top, want_row, want_pr, batch = 0, False, True, None
    if '--top' in args:
        i = args.index('--top')
        top = int(args[i + 1])
        del args[i:i + 2]
    for flag in ('--row', '--no-pr'):
        if flag in args:
            want_row = flag == '--row'
            want_pr = flag != '--no-pr'
            args.remove(flag)
    if '--batch' in args:
        i = args.index('--batch')
        batch = args[i + 1]
        del args[i:i + 2]
    opt = {}
    for k in ('--xlsx', '--tenhou', '--note', '--state'):
        if k in args:
            i = args.index(k)
            opt[k] = args[i + 1]
            del args[i:i + 2]
    if '--xlsx' in opt:
        for rid in args:
            m = re.search(r'\b([0-9a-f]{16})\b', rid)
            if m:
                append_xlsx(m.group(1), opt['--xlsx'], opt.get('--tenhou', ''), opt.get('--note', ''), opt.get('--state'))
        return
    if '--log' in args:
        i = args.index('--log')
        raw = args[i + 1]
        del args[i:i + 2]
        m = re.search(r'\b([0-9a-f]{16})\b', raw)
        if not m:
            print('--log 需要 Mortal 报告 id（16 位十六进制）或报告链接；天凤原始牌谱 JSON 不是 mjai 格式，log_stats 读不了。')
            return
        log_id = m.group(1)
        data = json.loads(_urlopen(f'https://mjai.ekyu.moe/report/{log_id}.json'))
        ls = log_stats(data)
        print(f'== {log_id}\n局数 {ls["kyoku"]} 和了 {ls["win"]}（{ls["win_rate"]:.1f}%）'
              f' 放铳 {ls["deal"]}（{ls["deal_rate"]:.1f}%）'
              f' 立直率 {ls["riichi_rate"]:.1f}% 副露率 {ls["meld_rate"]:.1f}%')
        return
    ids = list(args)
    if batch:
        ids += re.findall(r'\b[0-9a-f]{16}\b', open(batch, encoding='utf-8').read())
    for rid in dict.fromkeys(ids):
        try:
            if want_row:
                print(table_row(rid))
            else:
                print(report_one(rid, top, want_pr))
        except Exception as exc:
            print(f'== {rid}  失败: {exc}')
        print()


if __name__ == '__main__':
    main()
