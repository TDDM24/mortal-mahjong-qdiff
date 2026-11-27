#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Windows 侧「修复版算法」重跑的 56 场，替换旧数字后重算核心统计。

输入：
  data/原始数据/数据集_62场.csv      （旧算法 + 因变量 段位pt / 对手均R）
  data/重跑_56场_新算法.csv          （新算法，56 行，其中有 6 对重复行）

连接：优先用 天凤牌谱 == 旧表 logid；旧表 logid 缺失的 6 场用「日期+顺位」连（各唯一）。
输出：results，并打印 markdown，供写进论文/备忘。

用法： python3 recompute_new.py
"""
import re
import numpy as np
import pandas as pd

DATA = 'data/'


def norm_dt(s):
    s = str(s).strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2})\s*时', s)
    if m:
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}'
    m = re.match(r'(\d{1,2})/(\d{1,2})\s+(\d{1,2})\s*(?::\d{2})?\s*时?', s)
    if m:
        return f'2026-{int(m.group(1)):02d}-{int(m.group(2)):02d} {int(m.group(3)):02d}'
    return s


def pearson(x, y):
    return float(np.corrcoef(np.asarray(x, float), np.asarray(y, float))[0, 1])


def spearman(x, y):
    return float(np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1])


def pval(r, n):
    from math import sqrt, erf
    if abs(r) >= 1:
        return 0.0
    t = r * sqrt((n - 2) / (1 - r * r))
    return float(2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2)))))


def boot_ci(x, y, B=4000, seed=1):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), (B, len(x)))
    rs = [pearson(x[i], y[i]) for i in idx]
    return np.percentile(rs, [2.5, 97.5])


def load():
    old = pd.read_csv(DATA + '原始数据/数据集_62场.csv', encoding='utf-8-sig')
    new = pd.read_csv(DATA + '重跑_56场_新算法.csv', encoding='utf-8-sig')
    for d in (old, new):
        d['dt'] = d['日期'].map(norm_dt)
    new = (new.sort_values('序号')
              .drop_duplicates(subset=['天凤牌谱'], keep='first')
              .reset_index(drop=True))
    old['idx'] = range(len(old))
    return old, new


def match(old, new):
    byid = old.dropna(subset=['logid']).set_index('logid')
    pairs, unmatched = [], []
    for _, r in new.iterrows():
        lk = r['天凤牌谱']
        if isinstance(lk, str) and lk in byid.index:
            pairs.append((r.name, byid.loc[lk, 'idx'], 'logid'))
            continue
        c = old[(old['logid'].isna()) & (old['dt'] == r['dt']) & (old['顺位'] == r['顺位'])]
        if len(c) == 1:
            pairs.append((r.name, c.iloc[0]['idx'], 'date+rank'))
        else:
            unmatched.append((int(r['序号']), r['dt'], int(r['顺位']), len(c)))
    p = pd.DataFrame(pairs, columns=['ni', 'oi', 'how'])
    p = p.drop_duplicates(subset='oi')
    m = pd.concat([new.loc[p['ni']].reset_index(drop=True).add_prefix('新_'),
                   old.loc[p['oi']].reset_index(drop=True).add_prefix('旧_')], axis=1)
    return m, p, unmatched


def partial(x, y, z):
    def resid(a, b):
        A = np.c_[np.ones(len(b)), b]
        return a - A @ np.linalg.lstsq(A, a, rcond=None)[0]
    x, y, z = (np.asarray(v, float) for v in (x, y, z))
    ok = ~(np.isnan(x) | np.isnan(y) | np.isnan(z))
    return pearson(resid(x[ok], z[ok]), resid(y[ok], z[ok])), int(ok.sum())


def main():
    old, new = load()
    m, p, unmatched = match(old, new)
    m['pt'] = m['旧_pt']
    n = len(m)
    out = []
    add = out.append

    add(f'# 用新算法重跑后的重算结果\n')
    add(f'- 新表原始 {56} 行 → 去重后 {len(new)} 行（同一牌谱被重复提交，数字完全相同）')
    add(f'- 与旧 62 场连接：logid {int((p.how=="logid").sum())} 场 + 日期顺位 {int((p.how=="date+rank").sum())} 场 = **{n} 场**')
    add(f'- 未能连接的：{unmatched}（Windows 本机新记、不在旧清单里）\n')

    add('## 一、同一批 43 场：旧算法 vs 新算法\n')
    add('| 指标 | 旧 | 新 | 平均差 | 差的标准差 |')
    add('|---|---:|---:|---:|---:|')
    for a, b, name in [('合计失分', '合计失分', '合计失分'), ('严重失误', '严重失误', '严重失误'),
                       ('牌效', '牌效', '牌效'), ('防守', '防守', '防守'),
                       ('决策', '决策', '决策'), ('rating', 'rating', 'rating')]:
        d = m[f'新_{a}'] - m[f'旧_{b}']
        add(f'| {name} | {m[f"旧_{b}"].mean():.2f} | {m[f"新_{a}"].mean():.2f} | {d.mean():+.2f} | {d.std():.2f} |')

    add('\n## 二、与段位 pt 的相关（同一批 n=%d）\n' % n)
    add('| 指标 | r | 95% CI | ρ | p |')
    add('|---|---:|---|---:|---:|')
    for pref, label in [('新_严重失误', '严重失误（新）'), ('旧_严重失误', '严重失误（旧）'),
                        ('新_合计失分', '合计失分（新）'), ('旧_合计失分', '合计失分（旧）'),
                        ('新_牌效', '牌效（新）'), ('旧_牌效', '牌效（旧）'),
                        ('新_防守', '防守（新）'), ('旧_防守', '防守（旧）'),
                        ('新_rating', 'rating（新）'), ('旧_rating', 'rating（旧）')]:
        r = pearson(m[pref], m['pt'])
        ci = boot_ci(m[pref], m['pt'])
        add(f'| {label} | {r:+.3f} | [{ci[0]:+.2f}, {ci[1]:+.2f}] | {spearman(m[pref], m["pt"]):+.3f} | {pval(r, n):.3f} |')

    add('\n## 三、控制对手 R 的偏相关\n')
    add('| 指标 | 偏 r | n |')
    add('|---|---:|---:|')
    for pref, label in [('新_严重失误', '严重失误'), ('新_合计失分', '合计失分'), ('新_牌效', '牌效')]:
        rp, k = partial(m[pref], m['pt'], m['旧_oppR'])
        add(f'| {label} | {rp:+.3f} | {k} |')

    add('\n## 四、旧数据全样本（对照，n=%d）\n' % old['pt'].notna().sum())
    add('| 指标 | r | p | n |')
    add('|---|---:|---:|---:|')
    for c, label in [('严重失误', '严重失误'), ('合计失分', '合计失分'), ('牌效', '牌效'),
                     ('防守', '防守'), ('rating', 'rating'), ('每100次牌效决策', '每100次牌效决策')]:
        d = old.dropna(subset=[c, 'pt'])
        r = pearson(d[c], d['pt'])
        add(f'| {label} | {r:+.3f} | {pval(r, len(d)):.4f} | {len(d)} |')

    txt = '\n'.join(out) + '\n'
    with open('新算法重算_结果.md', 'w', encoding='utf-8') as f:
        f.write(txt)
    print(txt)
    m.to_csv('data/新旧配对_43场.csv', index=False, encoding='utf-8-sig')


if __name__ == '__main__':
    main()
