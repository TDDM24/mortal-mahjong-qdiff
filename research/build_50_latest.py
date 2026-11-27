#!/usr/bin/env python3
"""把「最新口径的 50 场指标」和「含 段位pt/对手R 的协变量表」拼成一份分析数据集。

来源：
- 指标（唯一权威）：`data/重跑_50场_新算法.csv`（Windows exe，beta2 口径，50/50 有牌谱链接，
  已按链接去重）。
- 协变量（因变量与对手强度）：`data/数据集_62场_新算法.csv`（95 列，含 pt / oppR / maxDiff）。

连接键：(月, 日, 时) + 决策数（同一小时两场靠决策数区分，不靠顺序），必要时再看顺位。
不用 报告ID：Windows 侧重取报告后有 18 个 id 变了。

用法：
    python3 research/build_50_latest.py
"""
import os
import re

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
METRICS = os.path.join(DATA, "重跑_50场_新算法.csv")
COVARS = os.path.join(DATA, "数据集_62场_新算法.csv")
OUT = os.path.join(DATA, "数据集_50场_最新口径.csv")
OUT_DEID = os.path.join(DATA, "数据集_50场_最新口径_去标识.csv")

# logid 是「那一场牌谱」的唯一标识，留在表里等于把对局公开，去标识版必须去掉
DROP_FOR_DEID = ["天凤牌谱", "tw", "报告ID", "logid", "备注", "日期来源"]
# 指标表里比 62 表新的列：用指标表覆盖
OVERWRITE = [
    "rating", "终局点数", "顺位", "决策",
    "合计失分", "牌效", "防守", "防守决策次数", "每100次防守决策", "严重失误",
    "副露压力下", "立直", "鸣牌", "牌效决策次数", "每100次牌效决策",
    "立直威胁次数", "立直威胁失分", "立直威胁sq",
    "隐形威胁次数", "隐形威胁失分", "隐形威胁sq",
    "压力分数(合并)", "和了率%", "放铳率%",
]


def parse_date(s):
    s = str(s).strip()
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        mo, d, rest = int(m.group(2)), int(m.group(3)), s[m.end():]
    else:
        m = re.search(r"(\d{1,2})[/-](\d{1,2})", s)
        if not m:
            return None
        mo, d, rest = int(m.group(1)), int(m.group(2)), s[m.end():]
    h = re.search(r"(\d{1,2})\s*[:时]", rest)
    return (mo, d, int(h.group(1)) if h else -1)


def main():
    met = pd.read_csv(METRICS, encoding="utf-8-sig")
    cov = pd.read_csv(COVARS, encoding="utf-8-sig")
    met["_k"] = met["日期"].map(parse_date)
    cov["_k"] = cov["日期"].map(parse_date)

    rows = []
    problems = []
    for i, r in met.iterrows():
        cand = cov[(cov["_k"] == r["_k"]) & (cov["决策"] == r["决策"])]
        if len(cand) > 1:
            cand = cand[cand["顺位"] == r["顺位"]]
        if len(cand) != 1:
            # 兜底：Windows 侧按牌谱 log id 校正过小时数（如 11/11 22时 vs 旧表 23时），
            # 同一天里「决策数 + 顺位」唯一时也认
            day = r["_k"][:2]
            cand = cov[(cov["_k"].map(lambda k: k[:2]) == day)
                       & (cov["决策"] == r["决策"]) & (cov["顺位"] == r["顺位"])]
        if len(cand) != 1:
            problems.append((r["日期"], r["决策"], len(cand)))
            continue
        row = cand.iloc[0].to_dict()
        for c in OVERWRITE:
            if c in met.columns:
                row[c] = r[c]
        row["天凤牌谱"] = r.get("天凤牌谱", row.get("天凤牌谱"))
        row["报告ID"] = r["报告ID"]
        # 英文镜像列（n/loss/severe/eff/def/effN/defN/winRate/dealRate）是给 pandas
        # 用的别名，必须跟着中文列走，否则会留下 v1.0 的旧值。
        row["指标来源"] = r.get("指标来源", row.get("指标来源", ""))
        # 这两场的报告在 mjai 上已 404、无法重算，所以指标用的是 62 场表里的旧记录。
        # 这 2 行在 Windows 重跑表里找不到对应场次，只能用 Mac 侧旧口径表的数字，
        # 口径不可比 → 标成「口径待核」，分析时默认剔除（analysis.py 的 STALE 列表）。
        src = str(row["指标来源"]).strip()
        row["指标口径"] = "beta2" if src in ("win重跑", "mac补算") else "口径待核"
        rows.append(row)

    df = pd.DataFrame(rows).drop(columns=["_k"], errors="ignore")
    MIRROR = {"n": "决策", "loss": "合计失分", "severe": "严重失误",
              "eff": "每100次牌效决策", "def": "每100次防守决策",
              "effN": "牌效决策次数", "defN": "防守决策次数",
              "winRate": "和了率%", "dealRate": "放铳率%"}
    for eng, cn in MIRROR.items():
        if eng in df.columns and cn in df.columns:
            df[eng] = df[cn]
    print(f"拼出 {len(df)} 行；配不上 {len(problems)} 行 {problems}")
    print(f"pt 非空 {df['pt'].notna().sum() if 'pt' in df else 0} 行；"
          f"oppR 非空 {df['oppR'].notna().sum() if 'oppR' in df else 0} 行")

    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    deid = df.drop(columns=[c for c in DROP_FOR_DEID if c in df.columns])
    deid.to_csv(OUT_DEID, index=False, encoding="utf-8-sig")
    print(f"写出 {OUT}（{df.shape[0]} 行 × {df.shape[1]} 列）")
    print(f"写出 {OUT_DEID}（{deid.shape[0]} 行 × {deid.shape[1]} 列）")


if __name__ == "__main__":
    main()
