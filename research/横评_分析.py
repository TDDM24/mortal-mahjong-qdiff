# -*- coding: utf-8 -*-
"""横评分析：读 横评_记录.csv，出 6.2 一致性 + 6.3 矩阵。

用法：
    python research/横评_分析.py

不依赖 pandas / scipy：Spearman 用秩相关手算，CI 用 Fisher z 近似。
只吃标准库，任何装了 Python 3.8+ 的机器都能跑。
"""
import csv
import io
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')
REC = os.path.join(DATA, '横评_记录.csv')
SAMPLE = os.path.join(DATA, '横评_场次.csv')
OUT = os.path.join(BASE, '横评_结果.md')

# 判定口径（照 工具横评方案.md 6.2）
NO_GAIN, PARTIAL = 0.8, 0.5


def read_csv(path):
    with io.open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def to_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def ranks(xs):
    """平均秩（处理并列）"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(xs, ys):
    n = len(xs)
    if n < 3:
        return None, None, n
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None, None, n
    rho = num / (dx * dy)
    # Fisher z 的 95% CI（n 小，仅作参考）
    ci = None
    if n > 3 and abs(rho) < 1:
        z = 0.5 * math.log((1 + rho) / (1 - rho))
        se = 1 / math.sqrt(n - 3)
        lo, hi = math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)
        ci = (lo, hi)
    return rho, ci, n


def verdict(rho, gap):
    if rho is None:
        return '样本不足'
    if abs(rho) > NO_GAIN:
        return f'同一把尺子（ρ绝对值>{NO_GAIN}，无增量）'
    if abs(rho) > PARTIAL:
        return f'部分重叠（ρ绝对值 {PARTIAL}~{NO_GAIN}，有增量）'
    if gap:
        return f'不同维度（ρ绝对值≤{PARTIAL}，有独立价值）'
    return '几乎没有关系'


def main():
    if not os.path.exists(REC):
        print('缺 %s，先跑 research/tools/gen_横评表.py' % REC)
        return 1
    rows = read_csv(REC)
    games = {g['序号']: g for g in read_csv(SAMPLE)}

    # 只统计有「覆盖=1」的行
    filled = [r for r in rows if (r.get('覆盖(0/1)') or '').strip() in ('1', '是', 'y')]
    tools = []
    for r in rows:
        t = r['工具']
        if t not in tools:
            tools.append(t)

    lines = ['# 工具横评结果', '',
             '数据：`research/data/横评_记录.csv`，样本 %d 场 × %d 个工具。' % (len(games), len(tools)),
             '生成脚本：`research/横评_分析.py`', '']

    if not filled:
        lines += ['> 记录表还是空的。先按 `research/横评_操作单.md` 把 10 场跑完填进来。', '']
        lines += ['## 每格要填什么', '',
                  '| 列 | 取值 | 含义 |', '|---|---|---|',
                  '| 覆盖(0/1) | 0/1 | 这一场这个工具是否成功跑出结果 |',
                  '| 粒度(0/1) | 0/1 | 能否看到逐手（不是只有整场汇总） |',
                  '| 可导出(0/1/2) | 0/1/2 | 0=只能截图 1=能复制文本 2=结构化文件 |',
                  '| 耗时分钟 | 数字 | 从上传到出结果的人工操作时间 |',
                  '| 可重复 | 一致/不一致/无法测 | 同一场跑两次关键数字是否一样 |',
                  '| 指标个数 | 整数 | 该工具给出几个可比较的指标 |',
                  '| 段位换算 | 0/1 | 是否把指标换算成段位/雀力 |',
                  '| 恶手分类 | 0/1 | 是否有恶手分类，且标准公开 |',
                  '| 失误或恶手读数 | 数字 | 该工具最接近「严重失误」的那个数字（用于一致性分析） |',
                  '']
    else:
        lines += ['## 1. 覆盖与能力（自动汇总）', '',
                  '| 工具 | 覆盖 | 可导出 | 平均耗时 | 指标数 | 段位换算 | 恶手分类 |',
                  '|---|---|---|---|---|---|---|']
        for t in tools:
            tr = [r for r in filled if r['工具'] == t]
            if not tr:
                lines.append('| %s | 0/10 | — | — | — | — | — |' % t)
                continue
            exp = max([to_float(r.get('可导出(0/1/2)')) or 0 for r in tr])
            cost = [to_float(r.get('耗时分钟')) for r in tr]
            cost = [c for c in cost if c is not None]
            metr = max([to_float(r.get('指标个数')) or 0 for r in tr])
            danki = max([to_float(r.get('段位换算(0/1)')) or 0 for r in tr])
            aku = max([to_float(r.get('恶手分类(0/1)')) or 0 for r in tr])
            lines.append('| %s | %d/10 | %d | %s | %d | %s | %s |' % (
                t, len(tr), int(exp), ('%.1f' % (sum(cost) / len(cost))) if cost else '—',
                int(metr), '有' if danki else '无', '有' if aku else '无'))

        lines += ['', '## 2. 与「严重失误」的一致性（Spearman）', '',
                  '用各工具的「失误or恶手读数」对本项目的「严重失误」做秩相关。', '',
                  '| 工具 | ρ | 95% CI | n | 判定 |', '|---|---|---|---|---|']
        for t in tools:
            tr = [r for r in filled if r['工具'] == t]
            xs, ys = [], []
            for r in tr:
                v = to_float(r.get('失误或恶手读数'))
                g = games.get(r['场次序号'])
                if v is None or not g:
                    continue
                s = to_float(g['严重失误'])
                if s is None:
                    continue
                xs.append(v)
                ys.append(s)
            rho, ci, n = spearman(xs, ys)
            gap = any('缺' in (r.get('备注') or '') for r in tr)
            lines.append('| %s | %s | %s | %d | %s |' % (
                t,
                ('%.3f' % rho) if rho is not None else '—',
                ('[%.2f, %.2f]' % ci) if ci else '—',
                n, verdict(rho, gap)))

        lines += ['', '## 3. 结论草稿', '',
                  '- ρ > 0.8 的工具：测的是同一件事，本项目**无增量**，README 里要如实写',
                  '- 0.5 < ρ ≤ 0.8：部分重叠，本项目的增量在「区间估计 / 纵向统计 / 混杂控制」',
                  '- ρ ≤ 0.5：不同维度，**有独立价值**，值得在论文里并列讨论', '',
                  '> 10 场样本只够描述，不能下统计结论。上面的 CI 只能当参考。']

    with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print('已写出 %s' % OUT)
    print('（已填行数：%d / %d）' % (len(filled), len(rows)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
