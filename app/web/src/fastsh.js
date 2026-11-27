// fastsh.py 的直译（92 行）：按"块"拆分 + 记忆化算向听。
// 块 = 同一花色里彼此相距不超过 2 的连续牌；字牌每种单独一块。
// 每个块只算一次它能组成的（面子, 搭子, 有无雀头）组合，存进缓存；整手牌把各块拼起来取最好。
const blockOptsCache = new Map();
const stdCache = new Map();

/** 返回 [[m,t,p], ...]，已按 (m,t,p) 排序；和 Python 的 _block_opts 一致 */
function blockOpts(counts, honor) {
  const key = `${honor ? 1 : 0}:${counts.join(',')}`;
  const hit = blockOptsCache.get(key);
  if (hit) return hit;
  const c = counts.slice();
  const n = c.length;
  const res = new Set();
  const dfs = (i, m, t, p) => {
    while (i < n && c[i] === 0) i += 1;
    if (i >= n) {
      res.add(`${m},${t},${p}`);
      return;
    }
    if (c[i] >= 3) {
      c[i] -= 3; dfs(i, m + 1, t, p); c[i] += 3;
    }
    if (!honor && i + 2 < n && c[i + 1] && c[i + 2]) {
      c[i] -= 1; c[i + 1] -= 1; c[i + 2] -= 1;
      dfs(i, m + 1, t, p);
      c[i] += 1; c[i + 1] += 1; c[i + 2] += 1;
    }
    if (c[i] >= 2) {
      if (!p) { c[i] -= 2; dfs(i, m, t, 1); c[i] += 2; }
      c[i] -= 2; dfs(i, m, t + 1, p); c[i] += 2;
    }
    if (!honor) {
      if (i + 1 < n && c[i + 1]) {
        c[i] -= 1; c[i + 1] -= 1; dfs(i, m, t + 1, p); c[i] += 1; c[i + 1] += 1;
      }
      if (i + 2 < n && c[i + 2]) {
        c[i] -= 1; c[i + 2] -= 1; dfs(i, m, t + 1, p); c[i] += 1; c[i + 2] += 1;
      }
    }
    c[i] -= 1; dfs(i, m, t, p); c[i] += 1;
  };
  dfs(0, 0, 0, 0);
  // 只留下不被别的组合完全压过的：同一个 (m,p) 只保留最大的 t
  const best = new Map();
  for (const s of res) {
    const [m, t, p] = s.split(',').map(Number);
    const k = `${m},${p}`;
    const prev = best.has(k) ? best.get(k) : -1;
    if (t > prev) best.set(k, t);
  }
  const out = [...best.entries()]
    .map(([k, t]) => {
      const [m, p] = k.split(',').map(Number);
      return [m, t, p];
    })
    .sort((x, y) => (x[0] - y[0]) || (x[1] - y[1]) || (x[2] - y[2]));
  if (blockOptsCache.size > 200000) blockOptsCache.clear();
  blockOptsCache.set(key, out);
  return out;
}

/** 把 34 张的计数拆成块：[{counts, honor}, ...] */
function blocks(c34) {
  const out = [];
  for (let s = 0; s < 3; s += 1) {
    const seg = c34.slice(s * 9, (s + 1) * 9);
    let i = 0;
    while (i < 9) {
      if (seg[i] === 0) { i += 1; continue; }
      let j = i;
      while (j + 1 < 9 && (seg[j + 1] || (j + 2 < 9 && seg[j + 2] && seg[j + 1] === 0))) j += 1;
      out.push({ counts: seg.slice(i, j + 1), honor: false });
      i = j + 1;
    }
  }
  for (let k = 27; k < 34; k += 1) {
    if (c34[k]) out.push({ counts: [c34[k]], honor: true });
  }
  return out;
}

/** 一般形向听（含副露数） */
function std(c34, melds) {
  const key = `${melds}:${c34.join(',')}`;
  const hit = stdCache.get(key);
  if (hit !== undefined) return hit;
  const need = 4 - melds;
  let states = new Set(['0,0,0']);
  for (const blk of blocks(c34)) {
    const opts = blockOpts(blk.counts, blk.honor);
    const next = new Set();
    for (const s of states) {
      const [m, t, p] = s.split(',').map(Number);
      for (const [bm, bt, bp] of opts) {
        if (p && bp) continue;
        next.add(`${Math.min(m + bm, 4)},${Math.min(t + bt, 8)},${p | bp}`);
      }
    }
    states = next;
  }
  let best = 8;
  for (const s of states) {
    let [m, t, p] = s.split(',').map(Number);
    m = Math.min(m, need);
    const tt = Math.min(t, need - m);
    best = Math.min(best, 2 * need - 2 * m - tt - p);
  }
  if (stdCache.size > 200000) stdCache.clear();
  stdCache.set(key, best);
  return best;
}

const YAO = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];
/** 向听数：一般形 + 七对子 + 国士。-1 = 和了，0 = 听牌 */
export function shanten34(c34in, melds = 0) {
  const c34 = c34in.map(Number);
  let s = std(c34, melds);
  if (melds === 0) {
    let pairs = 0;
    let kinds = 0;
    for (const x of c34) { if (x >= 2) pairs += 1; if (x) kinds += 1; }
    s = Math.min(s, 6 - pairs + Math.max(0, 7 - kinds));
    let k = 0;
    for (const i of YAO) if (c34[i]) k += 1;
    s = Math.min(s, 13 - k - (YAO.some((i) => c34[i] >= 2) ? 1 : 0));
  }
  return s;
}

/** 摸到哪些牌才可能让向听变化 */
export function related(c34, melds = 0) {
  const r = new Set();
  for (let i = 0; i < 27; i += 1) {
    if (!c34[i]) continue;
    const s = Math.floor(i / 9);
    for (const d of [-2, -1, 0, 1, 2]) {
      const j = i + d;
      if (j >= 0 && j < 27 && Math.floor(j / 9) === s) r.add(j);
    }
  }
  for (let i = 27; i < 34; i += 1) if (c34[i]) r.add(i);
  if (melds === 0) for (const i of YAO) r.add(i);
  return r;
}
