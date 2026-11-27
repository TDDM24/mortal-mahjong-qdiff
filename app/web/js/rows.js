// 一行数据的拼装（照 mr.py 的 build_row）、时间键（照 core.py 的 time_key）、CSV 导出
import { tenhouInfo, nowStamp } from '../src/mr.js';
import { pyRound } from '../src/pyround.js';

// 和 mr.py 的 XLSX_HEAD 一致，少一列「数据」（Excel 里那列是超链接，CSV 用不上）
export const HEAD = ['序号', '日期', '卓', '状态', '顺位', '终局点数', 'rating', '决策', '合计失分', '牌效', '防守',
  '防守决策次数', '每100次防守决策', '严重失误', '副露压力下', '立直', '鸣牌', '牌效决策次数',
  '每100次牌效决策', '立直威胁次数', '立直威胁失分', '立直威胁sq', '隐形威胁次数', '隐形威胁失分',
  '隐形威胁sq', '压力分数(合并)', '和了率%', '放铳率%', '天凤牌谱', 'tw', '报告ID', '口径', '备注'];

const r2 = (v) => pyRound(v, 2);
const r1 = (v) => pyRound(v, 1);
const r3 = (v) => pyRound(v, 3);

export function timeKey(log, date, no = 0) {
  let m = /^(\d{10})gm/.exec(log || '');
  if (m) return m[1] + String(Number(no || 0)).padStart(4, '0');
  m = /^(\d{4})-(\d{2})-(\d{2})(?:\D+(\d{1,2}))?/.exec(date || '');
  if (m) {
    return `${m[1]}${m[2]}${m[3]}${String(Number(m[4] || 0)).padStart(2, '0')}${String(Number(no || 0)).padStart(4, '0')}`;
  }
  m = /^(\d{1,2})\/(\d{1,2})(?:\s*(\d{1,2}))?/.exec(date || '');
  if (m) {
    const year = new Date().getFullYear();
    return `${year}${String(Number(m[1])).padStart(2, '0')}${String(Number(m[2])).padStart(2, '0')}${String(Number(m[3] || 0)).padStart(2, '0')}${String(Number(no || 0)).padStart(4, '0')}`;
  }
  return `9${String(Number(no || 0)).padStart(13, '0')}`;
}

/** 由一次计算的结果拼出「逐场」表的一行（键就是表头），和 mr.build_row 一致 */
export function buildRow(g, link = '', note = '', no = null) {
  const { s, pr, ls } = g;
  const [log, tw, when0] = tenhouInfo(link);
  let when = when0;
  if (!when) when = nowStamp();
  else if (!when.includes('时')) when = `${when} 00时`;
  return {
    序号: no,
    日期: when,
    卓: g.lobby || '',
    状态: '',
    顺位: g.rank,
    终局点数: g.score,
    rating: r1(g.rating),
    决策: s.n,
    合计失分: r2(s.loss),
    牌效: r2(s['牌效']),
    防守: r2(s['防守']),
    防守决策次数: s['防守_n'],
    // 一次防守都没有的场次记 null（记 0 会被当成「完美防守」污染平均与区间筛选）
    每100次防守决策: s['防守_n'] ? r1((s['防守_raw'] / s['防守_n']) * 100) : null,
    严重失误: r2(s.severe),
    副露压力下: r2(s['副露压力下']),
    立直: r2(s['立直判断']),
    鸣牌: r2(s['鸣牌判断']),
    牌效决策次数: s['牌效_n'],
    每100次牌效决策: s['牌效_n'] ? r1((s['牌效_raw'] / s['牌效_n']) * 100) : null,
    立直威胁次数: pr.riichi.n,
    立直威胁失分: r3(pr.riichi.loss),
    立直威胁sq: r3(pr.riichi.sq),
    隐形威胁次数: pr.hidden.n,
    隐形威胁失分: r3(pr.hidden.loss),
    隐形威胁sq: r3(pr.hidden.sq),
    '压力分数(合并)': pr.merged.n ? r1(pr.merged.per100) : null,
    '和了率%': r1(ls.win_rate),
    '放铳率%': r1(ls.deal_rate),
    天凤牌谱: log || '',
    tw: tw === null || tw === undefined ? '' : tw,
    报告ID: g.rid,
    口径: 'js',
    备注: note,
  };
}

function cell(v) {
  let s = v === null || v === undefined ? '' : String(v);
  // 公式注入：= + - @ 开头、或前面带制表符/空格的（Excel 会吃掉前缀）都要加单引号。
  // 先记下前导空白，判断完再还原，避免把 "  12.3" 这种正常数字也转义。
  const lead = s.match(/^[\s]*/)[0];
  const body = s.slice(lead.length);
  if (/^[=+\-@]/.test(body) && !Number.isFinite(Number(body))) s = `${lead}'${body}`;
  return (/[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
}

/** CSV（带 BOM，Excel 直接认 UTF-8） */
export function toCsv(rows) {
  const lines = [HEAD.map(cell).join(',')];
  for (const r of rows) lines.push(HEAD.map((h) => cell(r[h])).join(','));
  return `\ufeff${lines.join('\r\n')}\r\n`;
}
