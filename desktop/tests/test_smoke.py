# -*- coding: utf-8 -*-
"""可移植的自检：不依赖任何本机路径，临时目录里跑一遍核心链路。

用法：
    python tests/test_smoke.py
无头环境（CI）会自己加 QT_QPA_PLATFORM=offscreen。
"""
import os
import shutil
import sys
import tempfile

if 'QT_QPA_PLATFORM' not in os.environ and not (sys.platform == 'win32' or sys.platform == 'darwin'):
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = tempfile.mkdtemp(prefix='mahjong_smoke_')
os.environ['MAHJONG_HOME'] = HOME
sys.path.insert(0, ROOT)

ok = True


def check(name, cond, extra=''):
    global ok
    print(('PASS  ' if cond else 'FAIL  ') + name + (('  ' + str(extra)) if extra else ''))
    ok = ok and bool(cond)


from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

import core      # noqa: E402
import store     # noqa: E402


def fake_row(rid, seq=None):
    row = {h: '' for h in core.mr.XLSX_HEAD}
    row.update({'序号': seq, '日期': '2026-01-02 03时', '卓': '上级', '顺位': 1,
                '终局点数': 30000, 'rating': 85.0, '决策': 100, '合计失分': 8.0,
                '报告ID': rid, '备注': 'smoke'})
    return row


try:
    check('数据根目录落在临时目录', core.BASE == HOME, core.BASE)
    check('新库是空的', store.count() == 0, store.count())

    seq, existed = store.add_row(fake_row('0123456789abcdef'))
    check('插入一行', seq == 1 and not existed, (seq, existed))
    check('库里有 1 行', store.count() == 1, store.count())

    seq2, existed2 = store.add_row(fake_row('0123456789ABCDEF '))
    check('同一个 id（大写+空格）不再插入', existed2 is True and store.count() == 1, (seq2, existed2))
    check('按 id 能取回', (store.get('0123456789abcdef') or {}).get('卓') == '上级')

    store.add_row(fake_row('fedcba9876543210'))
    rows = store.all_rows()
    check('两行且序号递增', [r['序号'] for r in rows] == [1, 2], [r['序号'] for r in rows])

    out = os.path.join(HOME, '导出.xlsx')
    n = store.export_xlsx(out)
    check('导出成功', os.path.exists(out) and n == 2, n)
    import openpyxl
    wb = openpyxl.load_workbook(out)
    check('导出三页', wb.sheetnames[:3] == ['逐场', '汇总', '说明'], wb.sheetnames)
    ws = wb['逐场']
    check('导出行数 = 数据行 + 表头', ws.max_row == 3, ws.max_row)
    wb.close()

    from main_qt import MainWindow
    w = MainWindow()
    check('主窗口能创建', w.tabs.count() >= 2, w.tabs.count())
    w.set_theme_mode('dark')
    w.set_theme_mode('light')
    check('主题切换不炸', True)
    w.close()
finally:
    shutil.rmtree(HOME, ignore_errors=True)

print('\n' + ('ALL PASS' if ok else 'SOME FAILED'))
sys.exit(0 if ok else 1)
