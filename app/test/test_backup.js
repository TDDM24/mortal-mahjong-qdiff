import { readFileSync } from 'node:fs';
import { packBackup, unpackBackup, isGzip } from '../web/js/backup.js';

let pass = 0; let fail = 0;
const ok = (n, c, extra = '') => { if (c) pass += 1; else { fail += 1; console.log('FAIL ' + n + ' ' + extra); } };

const rep = JSON.parse(readFileSync('web/data/report_0b0d6c2336b144eb.json', 'utf8'));
const payload = { app: 'mahjong', version: 'v1.0.3', games: [{ rid: 'x', row: { 合计失分: 10.04 }, report: rep }] };

const packed = await packBackup(payload);
ok('默认走 gzip', packed.compressed === true, JSON.stringify(packed).slice(0, 80));
ok('扩展名', packed.ext === '.json.gz');
ok('mime', packed.mime === 'application/gzip');
ok('压缩后 < 60 KB', packed.sizeKB < 60, `${packed.sizeKB} KB`);
ok('原始 > 300 KB', packed.rawKB > 300, `${packed.rawKB} KB`);

// 往返
const bytes = Uint8Array.from(atob(packed.base64), (c) => c.charCodeAt(0));
ok('是 gzip 魔数', isGzip(bytes));
const back = await unpackBackup(bytes);
ok('往返后 game 数一致', back.games.length === 1);
ok('往返后报告字段还在', back.games[0].report.review.total_reviewed === rep.review.total_reviewed);
ok('往返后数值一致', back.games[0].row['合计失分'] === 10.04);
ok('往返后 mjai_log 长度一致', back.games[0].report.mjai_log.length === rep.mjai_log.length);

// 兼容旧的纯 JSON 备份
const plain = new TextEncoder().encode(JSON.stringify(payload));
ok('旧备份不是 gzip', isGzip(plain) === false);
const back2 = await unpackBackup(plain);
ok('旧备份能读', back2.games.length === 1);
const back3 = await unpackBackup(JSON.stringify(payload));
ok('直接给文本也能读', back3.games.length === 1);
const back4 = await unpackBackup(new TextEncoder().encode(JSON.stringify([{ rid: 'a' }])));
ok('数组形式的旧备份', back4.games.length === 1);

console.log(fail === 0
  ? `PASS 备份压缩：${pass} 条断言全部通过（${packed.rawKB} KB → ${packed.sizeKB} KB，省 ${(100 - packed.sizeKB / packed.rawKB * 100).toFixed(0)}%）`
  : `${fail} 条失败`);
if (fail) process.exitCode = 1;
