# -*- coding: utf-8 -*-
"""生成横评记录表（空格子，等人填）——从 横评_场次.csv 展开 6 个工具 x 10 场"""
import csv
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')
SAMPLE = os.path.join(DATA, '横评_场次.csv')

TOOLS = [
    ('Mortal', '基准，网页 mjai.ekyu.moe'),
    ('MAKA', '雀魂客户端内，5 次/天'),
    ('白くん', 'Chrome 扩展，跑在 Mortal 报告页'),
    ('BigCoach', '网页，需注册'),
    ('Gokujan', '网页，需注册'),
    ('mortal conveniencer', 'Chrome 扩展，写入 Google 表格'),
]

with io.open(SAMPLE, encoding='utf-8-sig') as f:
    games = list(csv.DictReader(f))

REC = os.path.join(DATA, '横评_记录.csv')
with io.open(REC, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['工具', '场次序号', '日期', '卓', '顺位', '分组',
                '覆盖(0/1)', '粒度(0/1)', '可导出(0/1/2)', '耗时分钟',
                '可重复(一致/不一致/无法测)', '指标个数', '段位换算(0/1)',
                '恶手分类(0/1)', '失误或恶手读数', '备注'])
    for tool, _ in TOOLS:
        for g in games:
            w.writerow([tool, g['序号'], g['日期'], g['卓'], g['顺位'], g['分组'],
                        '', '', '', '', '', '', '', '', '', ''])

SUM = os.path.join(DATA, '横评_汇总.csv')
with io.open(SUM, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['工具', '覆盖度(覆盖场次/10)', '可导出(0/1/2)', '平均耗时分钟',
                '指标个数', '段位换算(0/1)', '付费墙(0/1)', '一句话结论'])
    for tool, _ in TOOLS:
        w.writerow([tool, '', '', '', '', '', '', ''])

print('已生成:')
print(' ', REC, '->', len(TOOLS) * len(games), '行')
print(' ', SUM, '->', len(TOOLS), '行')
