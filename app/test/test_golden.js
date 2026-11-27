// 和 golden 文件逐字段比对。用法：node test/test_golden.js web/data/report_0b0d6c2336b144eb.json
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import { compute, toGolden } from '../web/src/core.js';
import { roundDeep } from '../web/src/pyround.js';

const reportPath = process.argv[2] || 'web/data/report_0b0d6c2336b144eb.json';
const rid = basename(reportPath).replace(/^report_/, '').replace(/\.json$/, '');
const goldenPath = process.argv[3] || `web/data/golden_${rid}.json`;

const report = JSON.parse(readFileSync(reportPath, 'utf8'));
const golden = JSON.parse(readFileSync(goldenPath, 'utf8'));

// golden 是 round(x, 4) 的结果；这里用同一个规则
const got = roundDeep(toGolden(compute(rid, report, { lobby: golden.lobby })));

const TOL = 1e-6;
const diffs = [];

function cmp(path, a, b) {
  if (typeof a === 'number' && typeof b === 'number') {
    if (Math.abs(a - b) > TOL) diffs.push(`${path}: 我 ${a} ≠ golden ${b}（差 ${(a - b).toExponential(3)}）`);
    return;
  }
  if (typeof a !== typeof b) { diffs.push(`${path}: 类型 ${typeof a} ≠ ${typeof b}（${a} / ${b}）`); return; }
  if (a === null || b === null) { if (a !== b) diffs.push(`${path}: ${a} ≠ ${b}`); return; }
  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b)) { diffs.push(`${path}: 一边不是数组`); return; }
    if (a.length !== b.length) diffs.push(`${path}: 长度 ${a.length} ≠ ${b.length}`);
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i += 1) cmp(`${path}[${i}]`, a[i], b[i]);
    return;
  }
  if (typeof a === 'object') {
    const ka = Object.keys(a).sort();
    const kb = Object.keys(b).sort();
    for (const k of ka) if (!kb.includes(k)) diffs.push(`${path}.${k}: golden 里没有这个键`);
    for (const k of kb) if (!ka.includes(k)) diffs.push(`${path}.${k}: 我没输出这个键`);
    for (const k of ka) if (kb.includes(k)) cmp(`${path}.${k}`, a[k], b[k]);
    return;
  }
  if (a !== b) diffs.push(`${path}: "${a}" ≠ "${b}"`);
}

cmp('$', got, golden);

const total = countLeaves(got);
function countLeaves(o) {
  if (o === null || typeof o !== 'object') return 1;
  if (Array.isArray(o)) return o.reduce((s, v) => s + countLeaves(v), 0);
  return Object.values(o).reduce((s, v) => s + countLeaves(v), 0);
}

if (diffs.length === 0) {
  console.log(`PASS  ${rid}: ${total} 个字段全部一致（容差 ${TOL}）`);
  console.log(`      n_decisions=${got.n_decisions}  five=${got.five.map((f) => f.value).join(' / ')}`);
} else {
  console.log(`FAIL  ${rid}: ${diffs.length} 处不一致`);
  for (const d of diffs.slice(0, 40)) console.log('  ' + d);
  if (diffs.length > 40) console.log(`  …… 还有 ${diffs.length - 40} 处`);
  process.exitCode = 1;
}
