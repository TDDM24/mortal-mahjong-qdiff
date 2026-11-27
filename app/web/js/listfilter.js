// 列表的筛选和分组（纯函数，能单独用 Node 测）
export const METRICS = [
  ['合计失分', '合计失分'],
  ['每100次牌效决策', '每100次牌效决策'],
  ['每100次防守决策', '每100次防守决策'],
  ['压力分数', '压力分数(合并)'],
  ['严重失误', '严重失误'],
];

/** "2026-11-26 09时" / "11/02 23:00" → "2026-11-26"；认不出返回 '' */
export function dateParts(s) {
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || '');
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = /^(\d{1,2})\/(\d{1,2})/.exec(s || '');
  if (m) {
    const y = new Date().getFullYear();
    return `${y}-${String(m[1]).padStart(2, '0')}-${String(m[2]).padStart(2, '0')}`;
  }
  return '';
}

export function hourLabel(s) {
  const m = /(\d{1,2})时/.exec(s || '');
  return m ? `${String(m[1]).padStart(2, '0')}时` : '';
}

/** 每一项在**库里已记录场次**里的最小/最大值；没数据返回 null（调用方据此禁用输入并提示） */
/** 严格取数：null/''/undefined 一律当缺失（Number(null) 是 0，会把空值当成「0 分」） */
function numOrNaN(raw) {
  if (raw === null || raw === undefined || raw === '') return NaN;
  return Number(raw);
}

export function metricBounds(games) {
  const b = {};
  for (const [, key] of METRICS) {
    const vals = games
      .map((g) => numOrNaN(g.row && g.row[key]))
      .filter((v) => Number.isFinite(v));
    b[key] = vals.length ? [Math.min(...vals), Math.max(...vals)] : null;
  }
  return b;
}

/** 库里的记录里，有可用指标（行数据齐全）的场次数 */
export function usableCount(games) {
  return games.filter((g) => g.row && Number.isFinite(Number(g.row['合计失分']))).length;
}

/** F = {from,to,lo:{},hi:{}}；空值表示不限 */
export function filteredGames(games, F) {
  return games.filter((g) => {
    const d = dateParts(g.date);
    if (d && F.from && d < F.from) return false;
    if (d && F.to && d > F.to) return false;
    for (const [, key] of METRICS) {
      const v = numOrNaN(g.row && g.row[key]);
      if (!Number.isFinite(v)) {
        // 这一项没有数据：只要设了区间，就不该混进结果
        const lo0 = F.lo[key]; const hi0 = F.hi[key];
        if ((lo0 !== undefined && lo0 !== '') || (hi0 !== undefined && hi0 !== '')) return false;
        continue;
      }
      const lo = F.lo[key];
      const hi = F.hi[key];
      if (lo !== undefined && lo !== '' && v < Number(lo)) return false;
      if (hi !== undefined && hi !== '' && v > Number(hi)) return false;
    }
    return true;
  });
}

/** 按日期分组，日期新的在前；组内按 seq 保持传入顺序（调用方先反转） */
export function groupByDate(games) {
  const m = new Map();
  for (const g of games) {
    const k = dateParts(g.date) || '未知日期';
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(g);
  }
  return [...m.entries()];
}
