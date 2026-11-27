// 输出一场的 JSON（和 golden 同结构）。用法：node test/dump.js web/data/report_xxx.json [out.json] [--lobby 上级]
import { readFileSync, writeFileSync } from 'node:fs';
import { basename } from 'node:path';
import { compute, toGolden } from '../web/src/core.js';
import { roundDeep } from '../web/src/pyround.js';

const args = process.argv.slice(2);
let lobby = '';
const li = args.indexOf('--lobby');
if (li >= 0) { lobby = args[li + 1]; args.splice(li, 2); }
const p = args[0] || 'web/data/report_0b0d6c2336b144eb.json';
const rid = basename(p).replace(/^report_/, '').replace(/\.json$/, '');
const out = roundDeep(toGolden(compute(rid, JSON.parse(readFileSync(p, 'utf8')), { lobby })));
const txt = JSON.stringify(out, null, 1);
if (args[1]) { writeFileSync(args[1], txt); console.log('written', args[1]); } else console.log(txt);
