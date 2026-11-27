// 把一场渲染成一个 HTML 文件，用浏览器打开看效果（这不是第 2 阶段的界面，只是让你确认渲染内容对不对）
// 用法：node test/preview.js web/data/report_0b0d6c2336b144eb.json
import { readFileSync, writeFileSync } from 'node:fs';
import { basename } from 'node:path';
import * as mr from '../web/src/mr.js';
import * as effaudit from '../web/src/effaudit.js';
import * as R from '../web/src/render.js';

const p = process.argv[2] || 'web/data/report_0b0d6c2336b144eb.json';
const rid = basename(p).replace(/^report_/, '').replace(/\.json$/, '');
const report = JSON.parse(readFileSync(p, 'utf8'));
const target = report.player_id;
const rows = mr.analyze(report);
const s = mr.summary(rows);
const [score, rank] = mr.finalScores(report);
const ls = mr.logStats(report);
const pr = mr.pressure(rows, target);
const five = [
  { name: '合计失分', value: s.loss, note: '' },
  { name: '每100次牌效决策', value: s['牌效_n'] ? (s['牌效_raw'] / s['牌效_n']) * 100 : 0, note: `${s['牌效_n']} 次` },
  { name: '每100次防守决策', value: s['防守_n'] ? (s['防守_raw'] / s['防守_n']) * 100 : null, note: `${s['防守_n']} 次` },
  { name: '压力分数', value: pr.merged.per100, note: `${pr.merged.n} 次` },
  { name: '严重失误', value: s.severe, note: `${Math.round((s.severe * s.n) / 100)} 次` },
];
const g = { rid, d: report, target, rows, s, score, rank, ls, pr, rating: report.review.rating * 100, five, lobby: mr.reportMeta(report).lobby };
const [n, ne, le, hands] = effaudit.classifyReport(report);
for (const h of hands) h.game = rid;
const res = effaudit.summarize([{ label: rid, n, ne, le, hands }]);

const css = `
body{font:14px/1.7 -apple-system,"PingFang SC",sans-serif;margin:0;padding:16px 18px 40px;color:#222;background:#fff;max-width:860px}
.h1{font-size:19px;font-weight:600;margin:10px 0 4px}
.h2{font-size:15px;font-weight:600;margin:18px 0 6px;color:#1f4e79}
.h3{font-weight:600;color:#1f4e79}
.dim{color:#888}
.bad{color:#c62828;font-weight:600}
.good{color:#2e7d32;font-weight:600}
.mortal{color:#2e7d32}
table{border-collapse:collapse;margin:6px 0}
table.five td,table.five th{padding:3px 14px 3px 0;text-align:left}
table.grid td,table.grid th{border:1px solid #ddd;padding:3px 10px}
td.k{color:#555}
p{margin:6px 0}
hr{border:0;border-top:1px solid #eee;margin:24px 0}
`;
const html = `<!doctype html><meta charset="utf-8"><title>${rid} · 预览</title><style>${css}</style>
${R.gameHtml(g, 10)}
<hr>
<div class="dim">下面是这一场的牌效审计（单场版）</div>
${R.auditHtml(res, [])}
`;
const out = `预览_${rid}.html`;
writeFileSync(out, html);
console.log('已生成', out);
console.log('用浏览器打开：open ' + out);
