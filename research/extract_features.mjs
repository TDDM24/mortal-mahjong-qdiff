#!/usr/bin/env node
/**
 * 从 Mortal 报告抽特征矩阵（每场一行）。
 *
 * 用法：
 *   node research/extract_features.mjs --rows rows.json --reports ./reports --out features.json
 *
 * rows.json 是 [{ "no": 1, "rid": "16位hex" }, ...]
 * 依赖 web/src/mr.js（与 Python 参考实现逐字段一致的那套计算核心）。
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const mr = await import(resolve(here, '../web/src/mr.js'));

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : def;
}
const rowsPath = arg('rows');
const reportsDir = arg('reports', resolve(here, '../web/data'));
const outPath = arg('out', resolve(here, 'features.json'));
if (!rowsPath) {
  console.error('缺少 --rows（形如 [{"no":1,"rid":"..."}] 的 JSON）');
  process.exit(2);
}

const rows = JSON.parse(readFileSync(rowsPath, 'utf8'));
const out = [];
let missing = 0;

for (const r of rows) {
  const rid = String(r.rid ?? r['报告ID'] ?? '').trim();
  if (rid.length !== 16) { out.push({ no: r.no ?? r['序号'], rid: null, missing: true }); missing += 1; continue; }
  const f = `${reportsDir}/${rid}.json`;
  if (!existsSync(f)) { out.push({ no: r.no, rid, missing: true }); missing += 1; continue; }

  const rep = JSON.parse(readFileSync(f, 'utf8'));
  const t = rep.player_id;
  const dec = mr.analyze(rep);
  const s = mr.summary(dec);
  const pr = mr.pressure(dec, t);
  const ls = mr.logStats(rep);

  const diffs = dec.map((d) => d.diff);
  const pos = diffs.filter((x) => x > 0).sort((a, b) => a - b);
  const bin = (lo, hi) => {
    const v = diffs.filter((x) => x >= lo && (hi === null || x < hi));
    return { n: v.length, sum: v.reduce((a, b) => a + b, 0) };
  };
  const jn = (lo, hi) => {
    const v = dec.filter((d) => d.junme >= lo && d.junme <= hi);
    return { n: v.length, sum: v.reduce((a, b) => a + b.diff, 0) };
  };
  const catJunme = (cat, lo, hi) => dec
    .filter((d) => d.cat === cat && d.junme >= lo && d.junme <= hi)
    .reduce((a, b) => a + b.diff, 0);
  const sorted = [...diffs].sort((a, b) => b - a);

  out.push({
    no: r.no, rid,
    n: s.n, loss: s.loss, severe: s.severe,
    eff: s['牌效'], def: s['防守'], fu2: s['副露压力下'], reach: s['立直判断'], call: s['鸣牌判断'],
    effN: s['牌效_n'], defN: s['防守_n'],
    b1_n: bin(0.1, 0.3).n, b1_sum: bin(0.1, 0.3).sum,
    b2_n: bin(0.3, 0.5).n, b2_sum: bin(0.3, 0.5).sum,
    b3_n: bin(0.5, 1).n, b3_sum: bin(0.5, 1).sum,
    b4_n: bin(1, null).n, b4_sum: bin(1, null).sum,
    maxDiff: sorted[0] || 0, p2nd: sorted[1] || 0,
    medPos: pos.length ? pos[Math.floor(pos.length / 2)] : 0,
    j13_n: jn(1, 3).n, j13_sum: jn(1, 3).sum,
    j49_n: jn(4, 9).n, j49_sum: jn(4, 9).sum,
    j10p_n: jn(10, 18).n, j10p_sum: jn(10, 18).sum,
    defEarly: catJunme('防守', 1, 9), defLate: catJunme('防守', 10, 18),
    effEarly: catJunme('牌效', 1, 3),
    prNone_n: pr.none.n, prNone_loss: pr.none.loss,
    prHidden_n: pr.hidden.n, prHidden_loss: pr.hidden.loss,
    prRiichi_n: pr.riichi.n, prRiichi_loss: pr.riichi.loss,
    winRate: ls.win_rate, dealRate: ls.deal_rate, riichiRate: ls.riichi_rate, meldRate: ls.meld_rate,
    kyoku: ls.kyoku,
  });
}

writeFileSync(outPath, JSON.stringify(out));
console.log(`抽出 ${out.length} 行；缺报告 ${missing} 行 → ${outPath}`);
