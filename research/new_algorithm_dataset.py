#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「新算法」的指标装回 62 场数据集，再重算核心统计。

指标来源优先级：
  1) data/重跑_56场_新算法.csv      Windows 重跑（44 场唯一，去重后）
  2) data/mac补算_新算法.csv        mac 用同一份修复版源码补算的 9 场（报告尚未过期）
  3) 旧算法                        其余场次（标记出来，不参与「新口径」统计）

连接键：天凤牌谱==logid → 报告ID → 日期+顺位（三者都要求一对一）。

输出：
  data/数据集_62场_新算法.csv      62 行，新增 指标来源 列
  新算法重算_结果.md               markdown 结果

用法： python3 new_algorithm_dataset.py
"""
import re
import numpy as np
import pandas as pd

D = 'data/'
COLS = ['决策', '合计失分', '严重失误', '牌效', '防守', '牌效决策次数', '防守决策次数',
        '压力分数', 'rating', '顺位', '终局点数']


def norm_dt(s):
    s = str(s).strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2})\s*时', s)
    if m:
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}'
    m = re.match(r'(\d{1,2})/(\d{1,2})\s+(\d{1,2})\s*(?::\d{2})?\s*时?', s)
    if m:
        return f'2026-{int(m.group(1)):02d}-{int(m.group(2)):02d} {int(m.group(3)):02d}'
    return s


def pear(x, y):
    return float(np.corrcoef(np.asarray(x, float), np.asarray(y, float))[0, 1])


def spear(x, y):
    return float(np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1])


def pv(r, n):
    from math import sqrt, erf
    if abs(r) >= 1:
        return 0.0
    t = r * sqrt((n - 2) / (1 - r * r))
    return float(2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2)))))


def ci(x, y, B=4000, seed=1):
    x, y = np.asarray(x, float), np.asarray(y, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), (B, len(x)))
    return np.percentile([pear(x[i], y[i]) for i in idx], [2.5, 97.5])


def attach(df, other, tag, used):
    """把 other 的指标贴到 df 上，返回未匹配到的 other 行。"""
    left = other[~other.index.isin(used)]
    if not len(left):
        return left
    idx_log = {v: i for i, v in df['logid'].items() if isinstance(v, str)}
    idx_rid = {v: i for i, v in df['报告ID'].items() if isinstance(v, str)}
    idx_dr = {}
    for i, r in df.iterrows():
        idx_dr.setdefault((r['dt'], r['顺位']), []).append(i)
    for i, r in left.iterrows():
        tgt = None
        if isinstance(r.get('天凤牌谱'), str) and r['天凤牌谱'] in idx_log:
            tgt = idx_log[r['天凤牌谱']]
        elif isinstance(r.get('报告ID'), str) and r['报告ID'] in idx_rid:
            tgt = idx_rid[r['报告ID']]
        else:
            cand = [j for j in idx_dr.get((r.get('dt'), r['顺位']), []) if j not in used]
            if len(cand) == 1:
                tgt = cand[0]
        if tgt is None or tgt in used:
            continue
        for c in COLS:
            if c in left.columns and pd.notna(r.get(c)):
                df.at[tgt, c] = r[c]
        df.at[tgt, '指标来源'] = tag
        used.add(tgt)
    return left


def main():
    old = pd.read_csv(D + '原始数据/数据集_62场.csv', encoding='utf-8-sig')
    win = pd.read_csv(D + '重跑_56场_新算法.csv', encoding='utf-8-sig')
    mac = pd.read_csv(D + 'mac补算_新算法.csv', encoding='utf-8-sig')
    win = win.rename(columns={'压力分数(合并)': '压力分数'})
    for d in (old, win):
        d['dt'] = d['日期'].map(norm_dt)
    mac['dt'] = ''
    win = win.sort_values('序号').drop_duplicates(subset=['天凤牌谱'], keep='first').reset_index(drop=True)
    old['指标来源'] = '旧算法'
    used = set()
    attach(old, win, 'win重跑', used)
    attach(old, mac.assign(天凤牌谱=None), 'mac补算', used)
    old.to_csv(D + '数据集_62场_新算法.csv', index=False, encoding='utf-8-sig')

    src = old['指标来源'].value_counts().to_dict()
    N = old[old['指标来源'] != '旧算法']
    out = []
    a = out.append
    a('# 新算法重装数据集后的重算结果\n')
    a(f'- 62 场里，指标已换成新算法：**{len(N)} 场**（{src}）')
    a(f'- 仍是旧算法的：**{len(old) - len(N)} 场**（报告已过期，只能重新提交牌谱才能重算）')
    a(f'- 连接方式：天凤牌谱=logid 优先，其次 报告ID，最后 日期+顺位\n')

    a('## 一、与段位 pt 的相关（新算法 n=%d）\n' % len(N))
    a('| 指标 | r | 95% CI | ρ | p |')
    a('|---|---:|---|---:|---:|')
    for c, label in [('严重失误', '严重失误'), ('合计失分', '合计失分'), ('牌效', '牌效'),
                     ('防守', '防守'), ('rating', 'rating'), ('压力分数', '压力分数')]:
        r = pear(N[c], N['pt'])
        lo, hi = ci(N[c], N['pt'])
        a(f'| {label} | {r:+.3f} | [{lo:+.2f}, {hi:+.2f}] | {spear(N[c], N["pt"]):+.3f} | {pv(r, len(N)):.3f} |')

    a('\n## 二、全 62 场（新旧混用，仅供对照）\n')
    a('| 指标 | r | p | n |')
    a('|---|---:|---:|---:|')
    for c in ['严重失误', '合计失分', '牌效', '防守', 'rating']:
        d = old.dropna(subset=[c, 'pt'])
        r = pear(d[c], d['pt'])
        a(f'| {c} | {r:+.3f} | {pv(r, len(d)):.4f} | {len(d)} |')

    a('\n## 三、分桌型（新算法场次）\n')
    a('| 桌 | n | 严重失误 r | 合计失分 r | pt 均值 |')
    a('|---|---:|---:|---:|---:|')
    for z, g in N.groupby('卓'):
        a(f'| {z} | {len(g)} | {pear(g["严重失误"], g["pt"]):+.3f} | {pear(g["合计失分"], g["pt"]):+.3f} | {g["pt"].mean():+.1f} |')

    txt = '\n'.join(out) + '\n'
    open('新算法重算_结果.md', 'w', encoding='utf-8').write(txt)
    print(txt)


if __name__ == '__main__':
    main()
