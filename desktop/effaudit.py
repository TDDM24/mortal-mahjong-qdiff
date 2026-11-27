"""牌效审计：把 Mortal 认为你打错的牌效手分成几类（用 fastsh 的快速向听）。

类别（只看 Q 差 ≥ 0.1、你和 Mortal 都是切牌的牌效决策）：
    该退没退   Mortal 那张打完向听更高（退向听），你的没退
    该进没进   Mortal 那张能进向听，你的没进
    进张算少   向听相同，Mortal 那张进张多 2 张以上
    Mortal 宁可少进张   向听相同，Mortal 那张进张反而少 2 张以上（为好形 / 打点）
    改良没看见 向听、进张都差不多，但 Mortal 那张之后靠改良能多出的进张明显更多
    其他       向听、进张、改良都差不多（打点、役、宝牌、安全度，或说不清）
"""
import collections
import fastsh
import mr

TI = mr.tile_index
CATS = ['进张算少', '改良没看见', 'Mortal 宁可少进张', '该进没进', '该退没退', '其他']


def _vis(snap, target, hand):
    v = collections.Counter(TI(x) for x in hand)
    if not snap:
        return v
    for p in range(4):
        for d in snap['kawa'][p]:
            if d.get('called'):
                continue
            v[TI(d['pai'])] += 1
        for m in snap['melds'][p]:
            # 自家的副露也要算可见：那几张已经不在手里，也不在牌山了。
            # hand 只有门前暗牌，不这样算会把自家碰的 3 张当成「牌山还有 4 张」。
            if m.get('type') == 'ankan':
                for x in m.get('consumed') or []:
                    if x:
                        v[TI(x)] += 1
                continue
            for x in [m.get('pai')] + list(m.get('consumed') or []):
                if x:
                    v[TI(x)] += 1
    for dm in snap['dora_markers']:
        v[TI(dm)] += 1
    return v


def _ukeire(c, melds, vis):
    sh = fastsh.shanten34(c, melds)
    u = 0
    for i in fastsh.related(c, melds):
        left = 4 - vis.get(i, 0)
        if left <= 0:
            continue
        c[i] += 1
        if fastsh.shanten34(c, melds) < sh:
            u += left
        c[i] -= 1
    return sh, u


def _gaizhi(c, melds, vis):
    sh, u = _ukeire(c, melds, vis)
    gain = 0
    for i in range(34):
        left = 4 - vis.get(i, 0)
        if left <= 0:
            continue
        c[i] += 1
        vis[i] += 1  # 试摸的这张也算可见，否则改良后的进张枚数会多算
        if fastsh.shanten34(c, melds) >= sh:
            best = u
            for t in range(34):
                if not c[t] or t == i:
                    continue
                c[t] -= 1
                s3, u3 = _ukeire(c, melds, vis)
                if s3 == sh and u3 > best:
                    best = u3
                c[t] += 1
            gain += left * (best - u)
        vis[i] -= 1
        c[i] -= 1
    return gain


def classify_report(rep):
    """返回 (这场全部决策数, 牌效决策数, 牌效失分, [分类后的手])"""
    target = rep['player_id']
    rows = mr.analyze(rep)
    eff = [r for r in rows if r['cat'] == '牌效']
    out = []
    for r in eff:
        if r['diff'] < 0.1 or r['actual'].get('type') != 'dahai' or r['expected'].get('type') != 'dahai':
            continue
        st = r['entry']['state']
        hand = st['tehai']
        melds = len(st.get('fuuros') or [])
        vis = _vis(r['snap'], target, hand)
        c = [0] * 34
        for x in hand:
            c[TI(x)] += 1
        ca = list(c); ca[TI(r['actual']['pai'])] -= 1
        cx = list(c); cx[TI(r['expected']['pai'])] -= 1
        sa, ua = _ukeire(ca, melds, vis)
        sx, ux = _ukeire(cx, melds, vis)
        if sx > sa:
            k = '该退没退'
        elif sx < sa:
            k = '该进没进'
        elif ux - ua >= 2:
            k = '进张算少'
        elif ux < ua - 1:
            k = 'Mortal 宁可少进张'
        else:
            k = '改良没看见' if _gaizhi(cx, melds, vis) > _gaizhi(ca, melds, vis) + 2 else '其他'
        out.append(dict(k=k, diff=r['diff'], sh=fastsh.shanten34(c, melds), junme=r['junme'],
                        kyoku=mr.kyoku_name(r['snap']), hand=hand, a=r['actual'], x=r['expected'],
                        sa=sa, ua=ua, sx=sx, ux=ux))
    return len(rows), len(eff), sum(r['diff'] for r in eff), out


def summarize(games):
    """games: [(标签, 决策数, 牌效决策数, 牌效失分, 手列表)] → 汇总字典"""
    n = sum(g[1] for g in games)
    ne = sum(g[2] for g in games)
    le = sum(g[3] for g in games)
    hands = [h for g in games for h in g[4]]
    by = collections.defaultdict(list)
    for h in hands:
        by[h['k']].append(h)
    cats = []
    for k in CATS:
        v = by.get(k, [])
        l = sum(h['diff'] for h in v)
        cats.append(dict(k=k, n=len(v), loss=l, share_eff=(l / le * 100 if le else 0),
                         per100=(l / n * 100 if n else 0),
                         big=sum(1 for h in v if h['diff'] >= 1.0), mid=sum(1 for h in v if h['diff'] >= 0.5)))
    bysh = collections.defaultdict(lambda: collections.Counter())
    for h in hands:
        bysh[min(h['sh'], 4)][h['k']] += h['diff']
    return dict(games=len(games), n=n, ne=ne, le=le, cats=cats, bysh=bysh, hands=hands)
