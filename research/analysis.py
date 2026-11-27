#!/usr/bin/env python3
"""
统计分析：复现论文 §6.4 的全部数字（n=50，beta2 口径）。

数据来源：`build_50_latest.py` 把「Windows exe 跑出的 50 场指标（beta2）」和
「62 场表里的 pt / 对手R 等协变量」拼成一份。旧算法（62 场）仍可用 --data 切换。

用法：
    python3 research/analysis.py                    # 用仓库内去标识数据集
    python3 research/analysis.py --data path.csv    # 用自己的数据
    python3 research/analysis.py --md results.md    # 同时写出 Markdown 报告

只依赖 numpy + pandas（不需要 scipy/statsmodels）。
"""
import argparse
import os
import re
from math import atanh, erfc, exp, lgamma, log, sqrt, tanh

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATES = [
    os.path.join(HERE, "data", "数据集_50场_最新口径_去标识.csv"),
    os.path.join(HERE, "数据集_50场_最新口径_去标识.csv"),   # 打包时 CSV 可能就在同级
]
DEFAULT = next((p for p in _CANDIDATES if os.path.exists(p)), _CANDIDATES[0])


# ---------------------------------------------------------------- 统计工具
def fisher_ci(r, n):
    """相关系数的 95% CI（Fisher z 变换）"""
    if n <= 3:
        return float("nan"), float("nan")
    z = atanh(max(min(r, 0.999999), -0.999999))
    se = 1 / sqrt(n - 3)
    return tanh(z - 1.96 * se), tanh(z + 1.96 * se)


def p_value(r, n):
    if n <= 3:
        return float("nan")
    z = atanh(max(min(r, 0.999999), -0.999999))
    return erfc(abs(z) * sqrt(n - 3) / sqrt(2))


def corr_table(df, y, xs):
    """逐变量：Pearson r + 95% CI + p + n"""
    out = []
    for x in xs:
        if x not in df.columns:
            continue
        q = df[[x, y]].dropna()
        n = len(q)
        if n < 5:
            continue
        r = np.corrcoef(q[x].astype(float), q[y].astype(float))[0, 1]
        lo, hi = fisher_ci(r, n)
        out.append(dict(var=x, n=n, r=r, lo=lo, hi=hi, p=p_value(r, n)))
    return pd.DataFrame(out)



def _betacf(a, b, x):
    """连分式（Numerical Recipes betacf），不装 scipy 也能算不完全 beta。"""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-12:
            break
    return h


def _betai(a, b, x):
    """正则化不完全 beta I_x(a,b)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = lgamma(a + b) - lgamma(a) - lgamma(b)
    front = exp(lbeta + a * log(x) + b * log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_sf(t, df):
    """t 分布双侧 p 值 P(|T| > t)，纯 Python 实现（不依赖 scipy）。"""
    if not np.isfinite(t):
        return float("nan")
    return _betai(df / 2.0, 0.5, df / (df + t * t))

def t_ppf(p, df):
    """t 分布分位数（二分法就够）。注意 t_sf 返回的是**双侧**尾概率。"""
    tail2 = 2.0 * (1.0 - p)
    lo, hi = 0.0, 200.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_sf(mid, df) > tail2:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def cluster_ols(y, X, groups):
    """OLS + 按组聚类的稳健标准误（CR1）"""
    X = np.column_stack([np.ones(len(X)), X])
    n, k = X.shape
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ b
    # 共线/全零列时 inv 会抛 LinAlgError，pinv 给出最小范数解，系数不可解释但不会崩
    XtXi = np.linalg.pinv(X.T @ X)
    meat = np.zeros((k, k))
    for g in np.unique(groups):
        m = groups == g
        s = X[m].T @ resid[m]
        meat += np.outer(s, s)
    G = len(np.unique(groups))
    # 只有一组（所有场次同一天）时 CR1 的 G/(G-1) 无定义，退回普通 OLS 标准误
    adj = (G / (G - 1)) if G > 1 else 1.0
    V = XtXi @ meat @ XtXi * adj * ((n - 1) / max(n - k, 1))
    se = np.sqrt(np.diag(V))
    t = b / se
    # 聚类数只有十几个，正态近似会把 p 压低约 3 倍；按 CR1 惯例用 t(G-1)
    p = [t_sf(abs(v), max(G - 1, 1)) for v in t]
    r2 = 1 - resid.var() / y.var()
    return dict(b=b, se=se, p=p, r2=r2, n=n, G=G)


def day_key(s):
    """聚类键 = 月/日。

    一律丢掉年份：早先带年份的行（"2026-11-23 21时"）会返回 "2026/11/23"，
    和 "11/23 21时" 派生的 "11/23" 变成两个聚类，G 从 19 虚增到 20，SE 被压低。
    """
    m = re.search(r"(?:\d{4})[/-](\d{1,2})[/-](\d{1,2})", str(s))
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})[/-](\d{1,2})", str(s))
    return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}" if m else "x"


def fmt_p(p):
    return "<0.001" if p < 0.001 else f"{p:.3f}"


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=DEFAULT)
    ap.add_argument("--md", default=None)
    args = ap.parse_args()

    df = pd.read_csv(args.data)
    lines = []
    say = lambda s="": (print(s), lines.append(s))

    say("# 分析结果（由 analysis.py 生成）")
    say()
    _shown = os.path.relpath(os.path.abspath(args.data), HERE)
    say(f"数据：`research/{_shown}`，{len(df)} 行 × {len(df.columns)} 列")
    y = "pt" if "pt" in df.columns else "段位pt"
    if "指标口径" in df.columns:
        STALE = ("旧算法", "报告404", "口径待核")   # 兼容改名前的 CSV
        stale = int(df["指标口径"].astype(str).isin(STALE).sum())
        if stale:
            df = df[~df["指标口径"].astype(str).isin(STALE)]
            say(f"剔除 `指标口径 = 口径待核` 的 {stale} 行"
                "（这些场次在 Windows 重跑表里找不到对应场次，"
                "只能用 Mac 侧旧口径数字，不可比）")
            say()
    d = df.dropna(subset=[y]).copy()
    if "日期" in d.columns:
        d["_day"] = d["日期"].apply(day_key)
    say(f"因变量 `{y}`（得点 = 素点 + ウマオカ，不是段位点）可用 {len(d)} 场")
    say()

    # 1) 单变量相关
    # 牌效/防守必须用「每 100 次该类决策」的口径（分母是 N_c），
    # 用原始失分和（分母是总决策数 N）会低估强度、也会和论文里的定义不一致。
    xs = ["严重失误", "压力分数(合并)", "合计失分", "maxDiff", "oppR",
          "每100次防守决策", "每100次牌效决策", "b4_n", "b1_sum"]
    # 缺列时 pandas 会在 dropna 里抛 KeyError: ['oppR']，看不出是"表不对"。
    # 先把缺的列名一次说清楚，再退出。
    need = [y] + xs
    missing = [c for c in need if c not in df.columns]
    if missing:
        say(f"**这张表缺列**：{('、'.join(missing))}。")
        say()
        say("本脚本要的数据是由 `build_50_latest.py` 生成的 `数据集_50场_最新口径_去标识.csv`；"
            "如果手工做了表，列名要和它一致（注意 `oppR` 是英文列名）。")
        return 2
    say("## 1. 单变量相关（因变量 = 单场得点，即素点 + ウマオカ；不是天凤段位点）")
    say()
    say("| 指标 | n | r | 95% CI | p |")
    say("|---|---|---|---|---|")
    ct = corr_table(d, y, xs)
    for _, row in ct.iterrows():
        say(f"| {row['var']} | {row['n']} | {row['r']:+.2f} | [{row['lo']:+.2f}, {row['hi']:+.2f}] | {fmt_p(row['p'])} |")
    say()

    # 2) 回归
    if "_day" in d.columns:
        say("## 2. 回归（按天聚类的稳健标准误）")
        say()
        models = [
            ("M1 只放对手R", ["oppR"]),
            ("M2 只放严重失误", ["严重失误"]),
            ("M3 严重失误 + 对手R", ["严重失误", "oppR"]),
            ("M4 五项 + 对手R", ["每100次牌效决策", "每100次防守决策", "严重失误", "oppR"]),
        ]
        # 桌型哑变量：上级卓 = 1
        if "卓" in d.columns:
            d["_high"] = (d["卓"].astype(str) == "上级").astype(float)
            models.append(("M5 严重失误 + 上级卓", ["严重失误", "_high"]))
        # 中介：加上和了/放铳（结果变量本身的一部分），看严重失误还剩多少
        if "和了率%" in d.columns and "放铳率%" in d.columns:
            models.append(("M6 严重失误 + 和了率 + 放铳率",
                           ["严重失误", "和了率%", "放铳率%"]))
        for label, cols in models:
            sub = d.dropna(subset=[y] + cols)
            if len(sub) < 10:
                continue
            res = cluster_ols(sub[y].values.astype(float),
                              sub[cols].values.astype(float),
                              sub["_day"].values)
            say(f"**{label}** · n={res['n']} 天={res['G']} R²={res['r2']:.3f}")
            say()
            say("| 变量 | 系数 | 聚类 SE | p | 标准化 |")
            say("|---|---|---|---|---|")
            for i, c in enumerate(cols):
                z = res["b"][i + 1] * sub[c].std() / sub[y].std()
                say(f"| {c} | {res['b'][i+1]:+.2f} | {res['se'][i+1]:.2f} | {fmt_p(res['p'][i+1])} | {z:+.2f} |")
            say()

    # 2b) 牌效的效应区间。口径必须跟 M4 一致：每 100 次该类决策，不能混用原始和
    cols2b = ["每100次牌效决策", "每100次防守决策", "严重失误", "oppR"]
    if all(c in d.columns for c in cols2b):
        sub = d.dropna(subset=[y] + cols2b)
        if len(sub) >= 10 and "_day" in sub.columns:
            res = cluster_ols(sub[y].values.astype(float),
                              sub[cols2b].values.astype(float),
                              sub["_day"].values)
            b, se, G = res["b"][1], res["se"][1], res["G"]
            tq = t_ppf(0.975, max(G - 1, 1))     # 和 p 值同分布：t(G-1)
            say("**牌效的效应区间**：每多 1 分「每100次牌效决策」对应 "
                f"{b:+.2f} 得点，95% CI（t({max(G - 1, 1)})）"
                f"[{b - tq * se:+.2f}, {b + tq * se:+.2f}]；n={res['n']}")
            say()
            say("注：这里的「分」是每 100 次牌效决策的失分，和五项指标里的「每100次牌效决策」同口径；"
                "不要和「牌效」原始和（合计失分的分量）混用。")
            say()

    # 2c) 信度：相邻两场配对 + Spearman–Brown 折算到 20 场
    say("## 2c. 信度（相邻两场配对，Spearman–Brown 折算到 20 场）")
    say()
    say("| 指标 | 相邻两场 r | 折算到 20 场 |")
    say("|---|---|---|")
    for c in ["合计失分", "严重失误", "每100次牌效决策", "每100次防守决策"]:
        if c not in d.columns:
            continue
        v = d.sort_values("日期")[c].dropna().values
        if len(v) < 8:
            continue
        a, b = v[0::2], v[1::2]
        k = min(len(a), len(b))
        if k < 4 or np.std(a[:k]) == 0 or np.std(b[:k]) == 0:
            continue
        r = float(np.corrcoef(a[:k], b[:k])[0, 1])
        r20 = 20 * r / (1 + 19 * r) if r > 0 else float("nan")
        say(f"| {c} | {r:+.2f} | {r20:.2f} |")
    say()
    say("注：配对方式是按日期排序后取奇/偶位置，样本少、误差大；它的作用是让 r₂₀ 这个数字可复现，"
        "不是精确估计。")
    say()

    # 3) 分桌型
    if "卓" in d.columns:
        say("## 3. 分桌型")
        say()
        say("| 桌型 | n | 合计失分 | 每100次防守 | 严重失误 | 每100次牌效 |")
        say("|---|---|---|---|---|---|")
        for z in d["卓"].dropna().unique():
            s = d[d["卓"] == z]
            vals = []
            for c in ["合计失分", "每100次防守决策", "严重失误", "每100次牌效决策"]:
                if c in s.columns:
                    q = s[[c, y]].dropna()
                    vals.append(f"{np.corrcoef(q[c], q[y])[0,1]:+.2f}" if len(q) > 3 else "—")
                else:
                    vals.append("—")
            say(f"| {z} | {len(s)} | " + " | ".join(vals) + " |")
        say()

    # 4) 拔线敏感性
    flag = next((c for c in ["有放置", "drop", "half"] if c in d.columns), None)
    if flag:
        say("## 4. 拔线敏感性")
        say()
        s = d[d[flag].fillna(0) == 0]
        say(f"剔除有放置/半放置的场次后：{len(s)} 场（原 {len(d)} 场）")
        say()
        say("| 指标 | r | 95% CI | n |")
        say("|---|---|---|---|")
        for _, row in corr_table(s, y, ["严重失误", "合计失分", "防守", "牌效"]).iterrows():
            say(f"| {row['var']} | {row['r']:+.2f} | [{row['lo']:+.2f}, {row['hi']:+.2f}] | {row['n']} |")
        say()

    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n→ 已写出 {args.md}")


if __name__ == "__main__":
    main()
