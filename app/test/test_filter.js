// 列表筛选/分组的单元测试：node test/test_filter.js
import { dateParts, metricBounds, filteredGames, groupByDate, hourLabel, usableCount } from '../web/js/listfilter.js';

let pass = 0; let fail = 0;
const eq = (name, a, b) => {
  const ok = JSON.stringify(a) === JSON.stringify(b);
  if (ok) { pass += 1; } else { fail += 1; console.log(`FAIL ${name}: ${JSON.stringify(a)} != ${JSON.stringify(b)}`); }
};

// 日期解析
eq('日期 完整', dateParts('2026-11-26 09时'), '2026-11-26');
eq('日期 只到日', dateParts('2026-11-26'), '2026-11-26');
eq('日期 旧格式', dateParts('11/02 23:00').length, 10);
eq('日期 认不出', dateParts('随便写的'), '');
eq('小时', hourLabel('2026-11-26 09时'), '09时');
eq('小时 没有', hourLabel('2026-11-26'), '');

const g = (seq, date, loss, eff, def, pr, sev) => ({
  seq, date, row: { 合计失分: loss, 每100次牌效决策: eff, 每100次防守决策: def, '压力分数(合并)': pr, 严重失误: sev },
});
const games = [
  g(1, '2026-11-01 21时', 8.0, 10.0, 12.0, 14.0, 1.0),
  g(2, '2026-11-01 22时', 12.0, 14.0, 18.0, 20.0, 3.0),
  g(3, '2026-11-02 19时', 6.5, 7.0, 5.0, 9.0, 0.5),
  g(4, '2026-11-26 09时', 7.55, 8.7, 1.0, 15.5, 2.88),
];

// 上下限
const b = metricBounds(games);
eq('合计失分范围', b['合计失分'], [6.5, 12]);
eq('压力分数范围', b['压力分数(合并)'], [9, 20]);

// 无筛选
eq('全部', filteredGames(games, { lo: {}, hi: {} }).length, 4);

// 日期区间
eq('11-01 当天', filteredGames(games, { from: '2026-11-01', to: '2026-11-01', lo: {}, hi: {} }).map((x) => x.seq), [1, 2]);
eq('11-01 到 11-02', filteredGames(games, { from: '2026-11-01', to: '2026-11-02', lo: {}, hi: {} }).map((x) => x.seq), [1, 2, 3]);
eq('只设起', filteredGames(games, { from: '2026-11-02', lo: {}, hi: {} }).map((x) => x.seq), [3, 4]);

// 5 项区间
eq('失分 ≤ 8', filteredGames(games, { lo: {}, hi: { 合计失分: 8 } }).map((x) => x.seq), [1, 3, 4]);
eq('失分 7–10', filteredGames(games, { lo: { 合计失分: 7 }, hi: { 合计失分: 10 }, }).map((x) => x.seq), [1, 4]);
eq('防守决策 ≥ 10', filteredGames(games, { lo: { 每100次防守决策: 10 }, hi: {} }).map((x) => x.seq), [1, 2]);
eq('组合：日期 + 失分', filteredGames(games, { from: '2026-11-01', to: '2026-11-26', lo: { 合计失分: 7 }, hi: { 合计失分: 9 }, }).map((x) => x.seq), [1, 4]);
eq('边界值含等号', filteredGames(games, { lo: { 合计失分: 12 }, hi: { 合计失分: 12 } }).map((x) => x.seq), [2]);
eq('空字符串当不限', filteredGames(games, { lo: { 合计失分: '' }, hi: { 合计失分: '' } }).length, 4);

// 空库 / 缺数据
eq('空库 bounds 为 null', metricBounds([])['合计失分'], null);
eq('空库可用数 0', usableCount([]), 0);
eq('缺行的记录不算可用', usableCount([{ seq: 9, date: '2026-11-01', row: null }, ...games].slice(0, 1)), 0);
eq('可用数', usableCount(games), 4);

// 分组
const groups = groupByDate([...games].reverse());
eq('分组日期顺序', groups.map(([d]) => d), ['2026-11-26', '2026-11-02', '2026-11-01']);
eq('同一天合并', groups[2][1].map((x) => x.seq), [2, 1]);

console.log(fail === 0 ? `PASS 筛选/分组：${pass} 条断言全部通过` : `${fail} 条失败 / 共 ${pass + fail} 条`);
if (fail) process.exitCode = 1;
