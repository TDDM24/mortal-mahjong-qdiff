// 输出渲染结果，用来和 Python 版逐字节比对：node test/render_dump.js <report.json>
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import * as mr from '../web/src/mr.js';
import * as effaudit from '../web/src/effaudit.js';
import * as R from '../web/src/render.js';

const p = process.argv[2];
if (process.argv[3] === 'lines') R.state.LINES_ON = true;
const rid = basename(p).replace(/^report_/, '').replace(/\.json$/, '');
const report = JSON.parse(readFileSync(p, 'utf8'));
const target = report.player_id;
const rows = mr.analyze(report);
const s = mr.summary(rows);
const [score, rank] = mr.finalScores(report);
const ls = mr.logStats(report);
const pr = mr.pressure(rows, target);
const eff = s['牌效_n'] ? (s['牌效_raw'] / s['牌效_n']) * 100 : 0;
const dfn = s['防守_n'] ? (s['防守_raw'] / s['防守_n']) * 100 : null;
const five = [
  { name: '合计失分', value: s.loss, note: '' },
  { name: '每100次牌效决策', value: eff, note: `${s['牌效_n']} 次` },
  { name: '每100次防守决策', value: dfn, note: `${s['防守_n']} 次` },
  { name: '压力分数', value: pr.merged.per100, note: `${pr.merged.n} 次` },
  { name: '严重失误', value: s.severe, note: `${Math.round((s.severe * s.n) / 100)} 次` },
];
const g = {
  rid, d: report, target, rows, s, score, rank, ls, pr,
  rating: report.review.rating * 100, five, lobby: mr.reportMeta(report).lobby,
};
const [n, ne, le, hands] = effaudit.classifyReport(report);
for (const h of hands) h.game = rid;
const res = effaudit.summarize([{ label: rid, n, ne, le, hands }]);
console.log('===GAME_HTML===');
console.log(R.gameHtml(g, 10));
console.log('===GAME_MD===');
process.stdout.write(R.gameMd(g, '', ''));
console.log('===AUDIT_HTML===');
console.log(R.auditHtml(res, []));
console.log('===ROW_HTML===');
for (const r of [...rows].sort((a, b) => b.diff - a.diff).slice(0, 3)) console.log(R.rowHtml(r, target));
