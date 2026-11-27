#!/usr/bin/env python3
"""
从「逐场记录表 + 牌谱 + Mortal 报告」构建分析数据集。

用法：
    python3 research/build_dataset.py \
        --rows  逐场数据.xlsx \
        --logs  raw/logs        # 每场一个 tenhou6 JSON：<logid>.json
        --reports raw/reports   # 每份一个 Mortal 报告：<reportid>.json
        --node  node \
        --out   research/data/数据集.csv

数据从哪里来：
  1. 逐场记录表：天凤/雀魂的对局汇总（序号、报告ID、牌谱 log id、tw 座位）
  2. 牌谱：https://tenhou.net/5/mjlog2json.cgi?<logid>  （公开，无需登录）
  3. 报告：https://mjai.ekyu.moe/report/<reportid>.json （提交牌谱后生成，15 天过期）

注意：仓库里**不含**原始牌谱与报告（含他人对局），需要自己准备。
本脚本从原始数据重建数据集；仓库内 `research/data/数据集_62场_去标识.csv`
就是用它跑出来的结果（去掉了牌谱/报告 id）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import pandas as pd

LOG_RE = re.compile(r"(\d{10}gm-[0-9a-f]{4}-\d{4}-[0-9a-f]{8})")
RID_RE = re.compile(r"\b([0-9a-f]{16})\b")


def parse_log(path, seat):
    """tenhou6 JSON → 顺位 / 终局 / 段位点变化 / 对手平均 R / 和了 / 放铳"""
    d = json.load(open(path, encoding="utf-8"))
    sc = d["sc"]
    scores = [sc[i * 2] for i in range(4)]
    pts = [sc[i * 2 + 1] for i in range(4)]
    order = sorted(range(4), key=lambda i: -scores[i])
    win = deal = 0
    for kyoku in d["log"]:
        for ev in kyoku:
            if isinstance(ev, list) and ev and ev[0] == "和了":
                # 双响/三响时后续和牌者依次在 ev[4]、ev[6]…，只检查 ev[2] 会漏
                for j in range(2, len(ev), 2):
                    info = ev[j]
                    if not isinstance(info, list) or len(info) < 2:
                        continue
                    if info[0] == seat:
                        win += 1
                    elif info[1] == seat:
                        deal += 1
    opp = [d["rate"][i] for i in range(4) if i != seat]
    return dict(
        rank_log=order.index(seat) + 1,
        score_log=scores[seat],
        pt=pts[seat],
        oppR=round(sum(opp) / 3, 1),
        dan=d["dan"][seat],
        myR=d["rate"][seat],
        win=win,
        deal=deal,
        disp=d["rule"].get("disp"),
        lobby=d.get("lobby"),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", required=True, help="逐场记录表（xlsx 或 csv）")
    ap.add_argument("--logs", required=True, help="牌谱目录：<logid>.json")
    ap.add_argument("--reports", required=True, help="报告目录：<reportid>.json")
    ap.add_argument("--node", default="node", help="node 可执行文件路径")
    ap.add_argument("--out", default="research/data/数据集.csv")
    args = ap.parse_args()

    for p in (args.rows, args.logs, args.reports):
        if not os.path.exists(p):
            sys.exit(f"找不到输入：{p}\n（仓库不含原始数据，见本文件顶部说明）")

    rows = pd.read_csv(args.rows) if args.rows.endswith(".csv") else pd.read_excel(args.rows)
    print(f"读入记录表：{len(rows)} 行")

    # 1) 牌谱侧
    log_rows = []
    for _, r in rows.iterrows():
        raw = str(r.get("天凤牌谱") or r.get("logid") or "")
        m = LOG_RE.search(raw)
        if not m:
            continue
        logid = m.group(1)
        path = os.path.join(args.logs, f"{logid}.json")
        if not os.path.exists(path):
            continue
        seat = r.get("tw")
        seat = int(seat) if pd.notna(seat) else 0
        try:
            log_rows.append(dict(序号=r["序号"], logid=logid, **parse_log(path, seat)))
        except Exception as e:  # noqa: BLE001
            print(f"  牌谱解析失败 {logid}: {e}")
    logs = pd.DataFrame(log_rows)
    print(f"  牌谱解析成功：{len(logs)} 场")

    # 2) 报告侧：交给 Node 抽特征
    pairs = [dict(no=int(r["序号"]), rid=str(r.get("报告ID") or "").strip())
             for _, r in rows.iterrows() if str(r.get("报告ID") or "").strip()]
    with tempfile.TemporaryDirectory() as tmp:
        rows_json = os.path.join(tmp, "rows.json")
        feat_json = os.path.join(tmp, "features.json")
        json.dump(pairs, open(rows_json, "w", encoding="utf-8"), ensure_ascii=False)
        script = os.path.join(os.path.dirname(__file__), "extract_features.mjs")
        ret = subprocess.run(
            [args.node, script, "--rows", rows_json,
             "--reports", args.reports, "--out", feat_json],
            capture_output=True, text=True,
        )
        print("  " + (ret.stdout or ret.stderr).strip())
        if ret.returncode != 0:
            sys.exit("Node 抽特征失败，检查 node 路径与报告目录")
        feats = pd.DataFrame(json.load(open(feat_json, encoding="utf-8")))

    # 3) 合并
    df = rows.merge(feats, left_on="序号", right_on="no", how="left").drop(columns=["no"], errors="ignore")
    if len(logs):
        drop = [c for c in df.columns if c in logs.columns and c != "序号"]
        df = df.drop(columns=drop, errors="ignore").merge(logs, on="序号", how="left")
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"\n→ {args.out}：{df.shape[0]} 行 × {df.shape[1]} 列")
    print(f"  有报告特征 {df['n'].notna().sum() if 'n' in df else 0} 场，有段位点 {df['pt'].notna().sum() if 'pt' in df else 0} 场")


if __name__ == "__main__":
    main()
