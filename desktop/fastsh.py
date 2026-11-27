"""快速向听：按"块"拆分 + 记忆化。
块 = 同一花色里彼此相距不超过 2 的连续牌（中间隔着 2 个以上空位就断开），字牌每种单独一块。
每个块只算一次它能组成的（面子数, 搭子数, 有无雀头）组合，存进缓存，以后同形状直接查表；
整手牌的向听 = 把各块的组合拼起来取最好。有雀头 / 无雀头 / 复杂形不用分开处理：
每个块同时记"拿雀头"和"不拿雀头"两种最优解，拼的时候自动选。"""
from functools import lru_cache

@lru_cache(maxsize=300000)
def _block_opts(counts, honor):
    """返回 {(m, t, p)} 的帕累托集合：这个块最多能拆出几个面子、几个搭子、是否含雀头。"""
    c = list(counts); n = len(c); res = set()
    def dfs(i, m, t, p):
        while i < n and c[i] == 0: i += 1
        if i >= n:
            res.add((m, t, p)); return
        if c[i] >= 3:
            c[i] -= 3; dfs(i, m + 1, t, p); c[i] += 3
        if not honor and i + 2 < n and c[i + 1] and c[i + 2]:
            c[i] -= 1; c[i + 1] -= 1; c[i + 2] -= 1; dfs(i, m + 1, t, p); c[i] += 1; c[i + 1] += 1; c[i + 2] += 1
        if c[i] >= 2:
            if not p:
                c[i] -= 2; dfs(i, m, t, 1); c[i] += 2
            c[i] -= 2; dfs(i, m, t + 1, p); c[i] += 2
        if not honor:
            if i + 1 < n and c[i + 1]:
                c[i] -= 1; c[i + 1] -= 1; dfs(i, m, t + 1, p); c[i] += 1; c[i + 1] += 1
            if i + 2 < n and c[i + 2]:
                c[i] -= 1; c[i + 2] -= 1; dfs(i, m, t + 1, p); c[i] += 1; c[i + 2] += 1
        c[i] -= 1; dfs(i, m, t, p); c[i] += 1
    dfs(0, 0, 0, 0)
    # 只留下不被别的组合完全压过的
    best = {}
    for m, t, p in res:
        k = (m, p); best[k] = max(best.get(k, -1), t)
    return tuple(sorted((m, t, p) for (m, p), t in best.items()))

def _blocks(c34):
    out = []
    for s in range(3):
        seg = c34[s * 9:(s + 1) * 9]; i = 0
        while i < 9:
            if seg[i] == 0: i += 1; continue
            j = i; gap = 0
            while j + 1 < 9 and (seg[j + 1] or (j + 2 < 9 and seg[j + 2] and seg[j + 1] == 0)):
                j += 1
            out.append((tuple(seg[i:j + 1]), False)); i = j + 1
    for k in range(27, 34):
        if c34[k]: out.append(((c34[k],), True))
    return out

@lru_cache(maxsize=300000)
def _std(c34, melds):
    need = 4 - melds
    states = {(0, 0, 0)}
    for blk, honor in _blocks(c34):
        opts = _block_opts(blk, honor); new = set()
        for m, t, p in states:
            for bm, bt, bp in opts:
                if p and bp: continue
                new.add((min(m + bm, 4), min(t + bt, 8), p | bp))
        states = new
    best = 8
    for m, t, p in states:
        m = min(m, need); tt = min(t, need - m)
        best = min(best, 2 * need - 2 * m - tt - p)
    return best

YAO = (0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33)

def shanten34(c34, melds=0):
    c34 = tuple(c34)
    s = _std(c34, melds)
    if melds == 0:
        pairs = sum(1 for x in c34 if x >= 2); kinds = sum(1 for x in c34 if x)
        s = min(s, 6 - pairs + max(0, 7 - kinds))
        k = sum(1 for i in YAO if c34[i])
        s = min(s, 13 - k - (1 if any(c34[i] >= 2 for i in YAO) else 0))
    return s

def related(c34, melds=0):
    """摸到哪些牌才可能让向听变化：手里有牌的周边 ±2，加上（门清时）幺九牌。其余的摸了也只是孤张。"""
    r = set()
    for i in range(27):
        if c34[i]:
            s = i // 9
            for d in (-2, -1, 0, 1, 2):
                j = i + d
                if 0 <= j < 27 and j // 9 == s: r.add(j)
    for i in range(27, 34):
        if c34[i]: r.add(i)
    if melds == 0: r.update(YAO)
    return r
