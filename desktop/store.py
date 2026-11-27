# -*- coding: utf-8 -*-
"""SQLite 存储：所有记录进库，Excel 只做导出。

要点：
- 每次操作开短连接，用完就关（否则 Windows 上 db 文件被占，没法备份/改名）
- seq 分配放在 IMMEDIATE 事务里，seq 上有 UNIQUE 索引，撞了就重试
- 导出的 xlsx 先写临时文件再 os.replace，避免写一半留下坏文件
"""
import contextlib
import datetime
import json
import logging
import os
import sqlite3

import core

DB_NAME = '麻将记录.db'

_SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seq INTEGER NOT NULL,
        report_id TEXT UNIQUE,
        date TEXT, zhuo TEXT, rank INTEGER, rating REAL, score INTEGER,
        data TEXT NOT NULL,
        created_at TEXT)''',
    'CREATE UNIQUE INDEX IF NOT EXISTS idx_seq ON games(seq)',
)


def db_path():
    return os.path.join(core.BASE, DB_NAME)


def log():
    return logging.getLogger('mahjong')


def _new_conn():
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA journal_mode=WAL')
    except sqlite3.Error:
        pass
    for sql in _SCHEMA:
        conn.execute(sql)
    conn.commit()
    return conn


@contextlib.contextmanager
def db():
    """短连接：进 with 开，出 with 关。"""
    conn = _new_conn()
    try:
        yield conn
    finally:
        conn.close()


def count(raise_on_error=False):
    try:
        with db() as conn:
            return conn.execute('SELECT COUNT(*) FROM games').fetchone()[0]
    except Exception:
        if raise_on_error:
            raise
        log().warning('读取数据库行数失败', exc_info=True)
        return 0


def next_seq(conn):
    return conn.execute('SELECT COALESCE(MAX(seq), 0) + 1 FROM games').fetchone()[0]


def norm_rid(v):
    return str(v or '').strip().lower()


def _find_same_log(conn, link, tw):
    """找同一副牌谱已经记过的那一行。

    同一副牌谱提交两次会拿到两个不同的报告 id，只能按链接挡。
    但链接必须**按字段精确比**：旧的 `link in old['data']` 是裸子串，
    备注里提到链接会误命中，同一半庄换个视角（tw 不同）会被误杀。
    """
    for old in conn.execute('SELECT seq, data FROM games'):
        try:
            d = json.loads(old['data'] or '{}')
        except Exception:
            continue
        if (str(d.get('天凤牌谱') or '').strip() == link
                and str(d.get('tw') or '').strip() == tw):
            return old['seq']
    return None


def add_row(row):
    """插入一行（按报告 id 去重）。返回 (序号, 是否已存在)。"""
    rid = norm_rid(row.get('报告ID'))
    row = dict(row)
    row['报告ID'] = rid
    link = str(row.get('天凤牌谱') or '').strip()
    tw = str(row.get('tw') or '').strip()
    with db() as conn:
        for _ in range(6):
            try:
                conn.execute('BEGIN IMMEDIATE')
                hit = conn.execute('SELECT seq FROM games WHERE report_id = ?', (rid,)).fetchone()
                if hit:
                    conn.commit()
                    return hit[0], True
                if link:
                    dup = _find_same_log(conn, link, tw)
                    if dup is not None:
                        conn.commit()
                        return dup, True
                seq = next_seq(conn)
                row['序号'] = seq
                conn.execute(
                    'INSERT INTO games (seq, report_id, date, zhuo, rank, rating, score, data, created_at)'
                    ' VALUES (?,?,?,?,?,?,?,?,?)',
                    (seq, rid, str(row.get('日期') or ''), str(row.get('卓') or ''),
                     row.get('顺位'), row.get('rating'), row.get('终局点数'),
                     json.dumps(row, ensure_ascii=False),
                     datetime.datetime.now().isoformat(timespec='seconds')))
                conn.commit()
                return seq, False
            except sqlite3.IntegrityError:
                conn.rollback()          # seq 被别人抢了，重算
            except Exception:
                conn.rollback()
                raise
        raise RuntimeError('写入冲突次数过多，请重试')


def all_rows():
    with db() as conn:
        cur = conn.execute('SELECT seq, data FROM games ORDER BY seq')
        out = []
        for r in cur:
            try:
                d = json.loads(r['data'])
            except Exception:
                log().warning('跳过损坏的一行 seq=%s', r['seq'])
                continue
            if not isinstance(d.get('序号'), int):
                d['序号'] = r['seq']
            out.append(d)
        return out


def get(rid):
    with db() as conn:
        r = conn.execute('SELECT data FROM games WHERE report_id = ?', (rid,)).fetchone()
        return json.loads(r['data']) if r else None


def _time_key(row):
    log_ = str(row.get('天凤牌谱') or '')
    date = str(row.get('日期') or '')
    no = row.get('序号') or 0
    return core.time_key(log_, date, no)


def games_for_audit():
    """给牌效审计用的轻量列表（按时间排序）。"""
    rows = all_rows()
    out = [dict(no=r.get('序号'), date=str(r.get('日期') or ''), zhuo=str(r.get('卓') or ''),
                rank=r.get('顺位'), rating=r.get('rating'), rid=r.get('报告ID'),
                key=_time_key(r)) for r in rows if r.get('报告ID')]
    out.sort(key=lambda x: x['key'])
    return out


def import_xlsx(path=None):
    """把旧的 Excel 搬进库（只导一次）。返回导入条数。"""
    import openpyxl
    path = path or core.XLSX
    if not os.path.exists(path):
        return 0
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if core.mr.XLSX_SHEET not in wb.sheetnames:
            return 0
        ws = wb[core.mr.XLSX_SHEET]
        it = ws.iter_rows(values_only=True)
        head = list(next(it))
        n = 0
        for r in it:
            row = {h: v for h, v in zip(head, r) if h is not None}
            row['报告ID'] = norm_rid(row.get('报告ID'))
            if not row.get('报告ID'):
                continue
            _, existed = add_row(row)
            if not existed:
                n += 1
        return n
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _xlsx_cell(v):
    """写进 Excel 的值。

    空字符串必须变 None：`汇总` 页用 SUMPRODUCT(...*L*M) 算加权均值，
    遇到 `0*""` 会整列 #VALUE!。
    以 = + - @ 开头的文本不能按公式写（Excel 会执行），这里只返回文本，
    由 `export_xlsx` 把单元格的 data_type 设成 's'（inlineStr）。
    不用前置单引号——那样 Excel 会把这个引号显示出来。
    """
    if v is None or v == '':
        return None
    if isinstance(v, str):
        text = v.lstrip()               # Excel 会吃掉前导制表符/空格，"\t=1+cmd" 照样执行
        if text[:1] in ('=', '+', '-', '@'):
            try:
                float(v)                # -1800、+3 这种是真数字，原样写
            except ValueError:
                return v                # 交给 export_xlsx 强制成文本
        return v
    return v


def _looks_formula(v):
    """这个值如果直接写进 Excel，会被当成公式吗？"""
    if not isinstance(v, str):
        return False
    text = v.lstrip()
    if text[:1] not in ('=', '+', '-', '@'):
        return False
    try:
        float(v)
        return False
    except ValueError:
        return True


def export_xlsx(path, template=None):
    """导出成 Excel：有旧文件就拿它当模板（保住「汇总」「说明」的公式），只重写「逐场」。"""
    import openpyxl
    rows = all_rows()
    template = template or core.XLSX
    sheet = core.mr.XLSX_SHEET
    src = None
    for cand in (template, path):
        if cand and os.path.exists(cand):
            src = cand
            break
    if src:
        try:
            wb = openpyxl.load_workbook(src)
        except Exception:
            wb = None            # 模板坏了（0 字节/不是 zip），当没有模板处理
        if wb is None:
            core.mr.new_workbook(path)
            wb = openpyxl.load_workbook(path)
        if sheet not in wb.sheetnames:
            raise RuntimeError(f'{os.path.basename(src)} 里没有「{sheet}」这张表，没法当模板')
    else:
        core.mr.new_workbook(path)
        wb = openpyxl.load_workbook(path)
    ws = wb[sheet]
    head = [c.value for c in ws[1]]
    if not head or head[0] is None:
        head = list(core.mr.XLSX_HEAD)
        ws.delete_rows(1, ws.max_row)
        ws.append(head)
    elif ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)
    for r in rows:
        vals = [_xlsx_cell(r.get(h)) for h in head]
        ws.append(vals)
        # append 会把 "=1+1" 当成公式存（data_type='f'），改成 inlineStr 才是纯文本。
        idx = ws.max_row
        for col, v in enumerate(vals, start=1):
            if _looks_formula(v):
                ws.cell(row=idx, column=col).data_type = 's'
    tmp = path + '.tmp'
    try:
        wb.save(tmp)
        os.replace(tmp, path)
    finally:
        try:
            wb.close()
        except Exception:
            pass
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
    return len(rows)
