import { splitChunks } from '../web/js/chunk.js';
let pass = 0; let fail = 0;
const ok = (name, cond) => { if (cond) pass += 1; else { fail += 1; console.log('FAIL ' + name); } };

const big = '麻将🐎'.repeat(20000);            // 3 个 UTF-16 单元一组，共 60000
const parts = splitChunks(big, 1000);
ok('拼回去一致', parts.join('') === big);
ok('每块不超过 size', parts.every((p) => p.length <= 1001));
ok('没有切开代理对', parts.every((p) => {
  const first = p.charCodeAt(0); const last = p.charCodeAt(p.length - 1);
  return !(first >= 0xDC00 && first <= 0xDFFF) && !(last >= 0xD800 && last <= 0xDBFF);
}));
ok('空串', splitChunks('', 10).length === 0);
ok('短于块大小', splitChunks('abc', 10).join('') === 'abc');
// 用真实备份文本再验一次
import { readFileSync } from 'node:fs';
const rep = JSON.parse(readFileSync('web/data/report_0b0d6c2336b144eb.json', 'utf8'));
const txt = JSON.stringify({ app: 'mahjong', games: [{ rid: 'x', report: rep }] }, null, 1);
const ps = splitChunks(txt, 32768);
ok('真实 JSON 拼回一致', ps.join('') === txt);
ok('真实 JSON 块数合理', ps.length > 10 && ps.length < 60);
const bytes = ps.reduce((s, p) => s + Buffer.byteLength(p, 'utf8'), 0);
ok('逐块 UTF-8 字节和 = 整体字节数', bytes === Buffer.byteLength(txt, 'utf8'));
console.log(fail === 0 ? `PASS 分块：${pass} 条断言全部通过（真实备份 ${ps.length} 块 / ${Math.round(Buffer.byteLength(txt,'utf8')/1024)} KB）` : `${fail} 条失败`);
if (fail) process.exitCode = 1;
