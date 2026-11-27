// effaudit.py 的直译：把 Mortal 认为你打错的牌效手分成 6 类
import { tileIndex as TI } from './tiles.js';
import * as fastsh from './fastsh.js';
import { analyze, kyokuName } from './mr.js';

export const CATS = ['进张算少', '改良没看见', 'Mortal 宁可少进张', '该进没进', '该退没退', '其他'];

function vis(snap, target, hand) {
  const v = new Map();
  const add = (i) => v.set(i, (v.get(i) || 0) + 1);
  for (const x of hand) add(TI(x));
  if (!snap) return v;
  for (let p = 0; p < 4; p += 1) {
    for (const d of snap.kawa[p]) if (!d.called) add(TI(d.pai));
    for (const m of snap.melds[p]) {
      // 自家的副露也要算可见：那几张已经不在手里，也不在牌山了。
      // hand（state.tehai）只有门前暗牌，不这样算会把自家碰的 3 张当成「牌山还有 4 张」。
      if (m.type === 'ankan') {
        for (const x of m.consumed || []) if (x) add(TI(x));
        continue;
      }
      for (const x of [m.pai, ...(m.consumed || [])]) {
        if (x) add(TI(x));
      }
    }
  }
  for (const dm of snap.dora_markers) add(TI(dm));
  return v;
}

function ukeire(c, melds, v) {
  const sh = fastsh.shanten34(c, melds);
  let u = 0;
  for (const i of fastsh.related(c, melds)) {
    const left = 4 - (v.get(i) || 0);
    if (left <= 0) continue;
    c[i] += 1;
    if (fastsh.shanten34(c, melds) < sh) u += left;
    c[i] -= 1;
  }
  return [sh, u];
}

function gaizhi(c, melds, v) {
  const [sh, u] = ukeire(c, melds, v);
  let gain = 0;
  for (let i = 0; i < 34; i += 1) {
    const left = 4 - (v.get(i) || 0);
    if (left <= 0) continue;
    c[i] += 1;
    v.set(i, (v.get(i) || 0) + 1); // 试摸的这张也算可见，否则改良后的进张枚数会多算
    if (fastsh.shanten34(c, melds) >= sh) {
      let best = u;
      for (let t = 0; t < 34; t += 1) {
        if (!c[t] || t === i) continue;
        c[t] -= 1;
        const [s3, u3] = ukeire(c, melds, v);
        if (s3 === sh && u3 > best) best = u3;
        c[t] += 1;
      }
      gain += left * (best - u);
    }
    v.set(i, v.get(i) - 1);
    c[i] -= 1;
  }
  return gain;
}

/** 返回 [这场全部决策数, 牌效决策数, 牌效失分, 分类后的手] */
export function classifyReport(rep) {
  const target = rep.player_id;
  const rows = analyze(rep);
  const eff = rows.filter((r) => r.cat === '牌效');
  const out = [];
  for (const r of eff) {
    if (r.diff < 0.1 || r.actual.type !== 'dahai' || r.expected.type !== 'dahai') continue;
    const st = r.entry.state;
    const hand = st.tehai;
    const melds = (st.fuuros || []).length;
    const v = vis(r.snap, target, hand);
    const c = new Array(34).fill(0);
    for (const x of hand) c[TI(x)] += 1;
    const ca = [...c]; ca[TI(r.actual.pai)] -= 1;
    const cx = [...c]; cx[TI(r.expected.pai)] -= 1;
    const [sa, ua] = ukeire(ca, melds, v);
    const [sx, ux] = ukeire(cx, melds, v);
    let k;
    if (sx > sa) k = '该退没退';
    else if (sx < sa) k = '该进没进';
    else if (ux - ua >= 2) k = '进张算少';
    else if (ux < ua - 1) k = 'Mortal 宁可少进张';
    else k = gaizhi(cx, melds, v) > gaizhi(ca, melds, v) + 2 ? '改良没看见' : '其他';
    out.push({
      k,
      diff: r.diff,
      sh: fastsh.shanten34(c, melds),
      junme: r.junme,
      kyoku: kyokuName(r.snap),
      hand,
      a: r.actual,
      x: r.expected,
      sa,
      ua,
      sx,
      ux,
    });
  }
  return [rows.length, eff.length, eff.reduce((s, r) => s + r.diff, 0), out];
}

/** games: [{label, n, ne, le, hands}] → 汇总 */
export function summarize(games) {
  const n = games.reduce((s, g) => s + g.n, 0);
  const ne = games.reduce((s, g) => s + g.ne, 0);
  const le = games.reduce((s, g) => s + g.le, 0);
  const hands = games.flatMap((g) => g.hands);
  const by = new Map();
  for (const h of hands) {
    if (!by.has(h.k)) by.set(h.k, []);
    by.get(h.k).push(h);
  }
  const cats = CATS.map((k) => {
    const v = by.get(k) || [];
    const l = v.reduce((s, h) => s + h.diff, 0);
    return {
      k,
      n: v.length,
      loss: l,
      share_eff: le ? (l / le) * 100 : 0,
      per100: n ? (l / n) * 100 : 0,
      big: v.filter((h) => h.diff >= 1).length,
      mid: v.filter((h) => h.diff >= 0.5).length,
    };
  });
  const bysh = new Map();
  for (const h of hands) {
    const key = Math.min(h.sh, 4);
    if (!bysh.has(key)) bysh.set(key, new Map());
    const m = bysh.get(key);
    m.set(h.k, (m.get(h.k) || 0) + h.diff);
  }
  return {
    games: games.length, n, ne, le, cats, bysh, hands,
  };
}
