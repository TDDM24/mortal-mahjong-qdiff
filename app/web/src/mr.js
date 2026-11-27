// mr.py 的直译：解析报告、对齐牌桌状态、分类决策、算指标。
// 函数名和 mr.py 一一对应，方便逐段对照。
import {
  HONORS, tileIndex, tileName, parseTile, pySum,
} from './tiles.js';

// ---------------------------------------------------------------- 二、向听
const shCache = new Map();

function shantenStd(counts, melds) {
  let best = 8;
  const c = counts;
  const dfs = (i, m, t, h) => {
    while (i < 34 && c[i] === 0) i += 1;
    if (i >= 34) {
      const mm = m + melds;
      const tt = Math.min(t, Math.max(0, 4 - mm));
      const v = 8 - 2 * mm - tt - h;
      if (v < best) best = v;
      return;
    }
    const r = i % 9;
    if (c[i] >= 3) { c[i] -= 3; dfs(i, m + 1, t, h); c[i] += 3; }
    if (i < 27 && r <= 6 && c[i + 1] && c[i + 2]) {
      c[i] -= 1; c[i + 1] -= 1; c[i + 2] -= 1;
      dfs(i, m + 1, t, h);
      c[i] += 1; c[i + 1] += 1; c[i + 2] += 1;
    }
    if (c[i] >= 2 && !h) { c[i] -= 2; dfs(i, m, t, 1); c[i] += 2; }
    if (c[i] >= 2) { c[i] -= 2; dfs(i, m, t + 1, h); c[i] += 2; }
    if (i < 27) {
      if (r <= 7 && c[i + 1]) {
        c[i] -= 1; c[i + 1] -= 1; dfs(i, m, t + 1, h); c[i] += 1; c[i + 1] += 1;
      }
      if (r <= 6 && c[i + 2]) {
        c[i] -= 1; c[i + 2] -= 1; dfs(i, m, t + 1, h); c[i] += 1; c[i + 2] += 1;
      }
    }
    c[i] -= 1; dfs(i, m, t, h); c[i] += 1;
  };
  dfs(0, 0, 0, 0);
  return best;
}

/** 向听数。-1 = 和了，0 = 听牌。melds 是副露组数。 */
export function shanten(tiles, melds = 0) {
  // 单视角牌谱里别人的暗牌是 '?'，tileIndex 返回 -1，必须剔掉
  const idx = tiles.map(tileIndex).filter((i) => i >= 0).sort((a, b) => a - b);
  const key = `${melds}:${idx.join(',')}`;
  const hit = shCache.get(key);
  if (hit !== undefined) return hit;
  const c = new Array(34).fill(0);
  for (const i of idx) c[i] += 1;
  let best = shantenStd(c.slice(), melds);
  if (melds === 0) {
    let pairs = 0;
    let kinds = 0;
    for (const x of c) { if (x >= 2) pairs += 1; if (x >= 1) kinds += 1; }
    best = Math.min(best, 6 - pairs + Math.max(0, 7 - kinds));
    const yao = [0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33];
    let k = 0;
    for (const i of yao) if (c[i]) k += 1;
    best = Math.min(best, 13 - k - (yao.some((i) => c[i] >= 2) ? 1 : 0));
  }
  // 上限：几千场批量跑时不至于把内存吃穿（桌面版同款 20 万）
  if (shCache.size > 200000) shCache.clear();
  shCache.set(key, best);
  return best;
}

/** 听哪些牌（0..33 的 Set）。kawa 里出现过的算振听，不计。 */
export function waitingTiles(tiles, melds = 0, kawa = new Set()) {
  const out = new Set();
  const cnt = new Array(34).fill(0);
  for (const t of tiles) cnt[tileIndex(t)] += 1;
  for (let i = 0; i < 34; i += 1) {
    if (cnt[i] >= 4) continue; // 手里四张了，第 5 张是虚听
    if (shanten([...tiles, tileName(i)], melds) === -1) out.add(i);
  }
  // 舍张振听：任意一张待牌在自己牌河里，整手牌都不能荣和
  for (const k of kawa) if (out.has(k)) return new Set();
  return out;
}

// ---------------------------------------------------------------- 三、回放
class State {
  constructor() {
    this.ordinal = 0;
    this.bakaze = 'E'; this.kyoku = 1; this.honba = 0; this.oya = 0;
    this.scores = [25000, 25000, 25000, 25000];
    this.dora_markers = [];
    this.tehai = [[], [], [], []];
    this.kawa = [[], [], [], []];
    this.melds = [[], [], [], []];
    this.riichi = [false, false, false, false];
    this.riichi_junme = [null, null, null, null];
    this.riichi_seq = [null, null, null, null];
    this.junme = [0, 0, 0, 0];
    this.n_kan = 0;
  }

  snapshot() {
    return {
      ordinal: this.ordinal,
      bakaze: this.bakaze,
      kyoku: this.kyoku,
      honba: this.honba,
      oya: this.oya,
      scores: [...this.scores],
      dora_markers: [...this.dora_markers],
      tehai: this.tehai.map((t) => [...t]),
      kawa: this.kawa.map((k) => k.map((d) => ({ ...d }))),
      melds: this.melds.map((p) => p.map((m) => ({ ...m, consumed: [...(m.consumed || [])] }))),
      riichi: [...this.riichi],
      riichi_junme: [...this.riichi_junme],
      riichi_seq: [...this.riichi_seq],
      junme: this.junme.map((x) => x + 1),
      n_kan: this.n_kan,
    };
  }
}

function canCall(snap, target, actor, discard) {
  if (actor === target || snap.riichi[target] || snap.melds[target].length >= 4) return false;
  const hand = new Array(34).fill(0);
  for (const t of snap.tehai[target]) hand[tileIndex(t)] += 1;
  const d = tileIndex(discard);
  if (hand[d] >= 2) return true;
  const [suit, n] = parseTile(discard);
  if (suit !== 'z' && (actor + 1) % 4 === target) {
    for (const delta of [-2, -1, 1, 2]) {
      const nn = n + delta;
      if (nn >= 1 && nn <= 9) {
        const lo = Math.min(n, nn);
        const need = [];
        for (let x = lo; x < lo + 3; x += 1) if (x !== n) need.push(tileIndex(`${x}${suit}`));
        if (need.length === 2 && need.every((t) => hand[t])) return true;
      }
    }
  }
  return false;
}

/** 回放牌谱，产出 target 的每个决策点 */
export function decisions(log, target) {
  const out = [];
  let st = null;
  let ordinal = -1;
  let postCall = false;
  log.forEach((ev, idx) => {
    const typ = ev.type;
    if (typ === 'start_kyoku') {
      ordinal += 1;
      st = new State();
      st.ordinal = ordinal;
      st.bakaze = ev.bakaze; st.kyoku = ev.kyoku; st.honba = ev.honba; st.oya = ev.oya;
      st.scores = [...ev.scores];
      st.dora_markers = [ev.dora_marker];
      st.tehai = ev.tehais.map((t) => [...t]);
      return;
    }
    if (!st) return;
    if (typ === 'tsumo') {
      const a = ev.actor;
      st.tehai[a].push(ev.pai);
      if (a === target && !st.riichi[a]) out.push({ kind: 'tsumo', idx, snap: st.snapshot(), tile: ev.pai, actor: a });
    } else if (typ === 'dahai') {
      const a = ev.actor;
      const pai = ev.pai;
      // 鸣牌后、切牌前的那一手：Mortal 的 state.tehai 是切牌前的 11/8/5 张，
      // 所以快照必须在改手牌/牌河/巡目之前拍，否则精确匹配 100% 失败。
      if (a === target && postCall) out.push({ kind: 'post_call', idx, snap: st.snapshot(), tile: pai, actor: a });
      const at = st.tehai[a].indexOf(pai);
      if (at >= 0) st.tehai[a].splice(at, 1);
      st.kawa[a].push({
        pai, tsumogiri: ev.tsumogiri === undefined ? false : !!ev.tsumogiri,
        riichi: st.riichi[a], junme: st.junme[a] + 1, seq: idx, actor: a,
      });
      st.junme[a] += 1;
      if (a !== target && canCall(st.snapshot(), target, a, pai)) {
        out.push({ kind: 'call', idx, snap: st.snapshot(), tile: pai, actor: a });
      }
      postCall = false;
    } else if (typ === 'chi' || typ === 'pon' || typ === 'daiminkan') {
      const a = ev.actor;
      for (const c of ev.consumed || []) {
        const i = st.tehai[a].indexOf(c);
        if (i >= 0) st.tehai[a].splice(i, 1);
      }
      st.melds[a].push({ type: typ, pai: ev.pai, consumed: [...(ev.consumed || [])], from: ev.target });
      const src = ev.target;
      if (src !== undefined && src !== null && st.kawa[src].length) {
        // 被鸣走的牌仍然是打牌者的舍牌（现物、舍张振听的依据），不能删，只标记 called，
        // visible() 统计可见枚数时跳过它（已经算在副露里了）。
        const d = st.kawa[src][st.kawa[src].length - 1];
        if (d && (d.pai === ev.pai || tileIndex(d.pai) === tileIndex(ev.pai))) d.called = true;
        else st.kawa[src].pop();
      }
      // 吃/碰之后立刻切牌，需要 post_call 点；大明杠之后先摸岭上牌，由 tsumo 点覆盖
      if (a === target && typ !== 'daiminkan') postCall = true;
    } else if (typ === 'ankan' || typ === 'kakan') {
      const a = ev.actor;
      for (const c of ev.consumed || []) {
        const i = st.tehai[a].indexOf(c);
        if (i >= 0) st.tehai[a].splice(i, 1);
      }
      if (typ === 'kakan') {
        // 加杠：pai 是手牌里的第 4 张（必须先删掉），consumed 是原来碰的 3 张（已经在 meld 里，不能再追加）
        const ip = st.tehai[a].indexOf(ev.pai);
        if (ip >= 0) st.tehai[a].splice(ip, 1);
        let merged = false;
        for (const m of st.melds[a]) {
          if (m.type === 'pon' && tileIndex(m.pai) === tileIndex(ev.pai)) {
            m.type = 'kakan';
            m.consumed = [...(m.consumed || []), ev.pai];
            merged = true;
            break;
          }
        }
        if (!merged) {
          st.melds[a].push({ type: typ, pai: ev.pai, consumed: [...(ev.consumed || []), ev.pai], from: a });
        }
      } else {
        // 暗杠事件没有 pai 字段（mjai 标准），用 consumed[0] 占位，visible() 里按 consumed 计数
        st.melds[a].push({ type: typ, pai: ev.pai || (ev.consumed || [])[0], consumed: [...(ev.consumed || [])], from: a });
      }
      st.n_kan += 1;
    } else if (typ === 'hora') {
      // 和了/见逃也是一次决策：和了就地和；见逃则接着打。快照就是「和了那一刻」的手牌
      // （自摸 14 张、荣和 13 张，副露后按 13−3×副露数）
      if (ev.actor === target) {
        out.push({ kind: 'hora', idx, snap: st.snapshot(), tile: ev.pai || null, actor: ev.actor });
      }
    } else if (typ === 'reach') {
      const a = ev.actor;
      st.riichi[a] = true;
      st.riichi_junme[a] = st.junme[a];
      st.riichi_seq[a] = idx;
    } else if (typ === 'dora') {
      st.dora_markers.push(ev.dora_marker);
    } else if (typ === 'end_kyoku') {
      st = null;
    }
  });
  return out;
}

// ---------------------------------------------------------------- 四、对齐
/** 把 action 变成可比较的字符串键（Python 里用 tuple 当 dict key） */
export function actKey(a, plain = false) {
  const t = a.type;
  // plain=true 用于「宽松匹配」：忽略摸切/手切、赤五、副露顺序这三个 Mortal 与我们口径不一致的点
  const n = (x) => (plain ? String(x || '').replace(/r/g, '') : x);
  if (t === 'dahai') return plain ? `dahai|${n(a.pai)}` : `dahai|${a.pai}|${a.tsumogiri ? 1 : 0}`;
  if (t === 'none') return 'none';
  const cons = (a.consumed || []).map(n).sort().join(',');
  return plain ? `${t}|${n(a.pai)}|${cons}` : `${t}|${a.pai}|${(a.consumed || []).join(',')}`;
}

/** 在 details 里挑一个动作的 Q：精确 → 宽松 → Mortal 给的 actual_index 兜底 */
function pickQ(exact, relaxed, act, details, idx) {
  const v = exact.get(actKey(act));
  if (v !== undefined) return v;
  // 其次用报告自带的 actual_index：它是 Mortal 自己算出来的，比任何模糊键都准。
  // 曾经把 relaxed 放在这里，结果手里同时有 5p 和 5pr 时，去赤五的键会把两者
  // 合成同一个键，取到另一张牌的 Q（实测 38 份报告 28 处，最大差 1.6）。
  if (Number.isInteger(idx) && details[idx]) return details[idx].q_value;
  const w = relaxed.get(actKey(act, true));
  if (w !== undefined) return w;
  return undefined;
}

function handKey(tiles) {
  return tiles.map(tileIndex).sort((a, b) => a - b).join(',');
}

function alignKyoku(entries, points, target) {
  const n = entries.length;
  const m = points.length;
  const NEG = -1e9;
  const match = new Array(n).fill(null);
  const used = new Array(m).fill(false);
  let cur = 0;
  for (let i = 0; i < n; i += 1) {
    const want = handKey(entries[i].state.tehai);
    let hit = -1;
    for (let j = cur; j < m; j += 1) {
      if (!used[j] && handKey(points[j].snap.tehai[target]) === want) { hit = j; break; }
    }
    if (hit >= 0) {
      match[i] = points[hit];
      used[hit] = true;
      cur = hit + 1;
      continue;
    }
    // 立直宣言与立直切牌是同一个 14 张手牌的两次询问，共用一个快照。
    // 只对 at_self_riichi 放行；别的 entry 复用会掩盖真正的错位。
    if (entries[i].at_self_riichi) {
      for (let j = Math.max(0, cur - 4); j < m; j += 1) {
        if (used[j] && handKey(points[j].snap.tehai[target]) === want) { match[i] = points[j]; break; }
      }
    }
  }
  const restE = [];
  for (let i = 0; i < n; i += 1) if (!match[i]) restE.push(i);
  const restP = [];
  for (let j = 0; j < m; j += 1) if (!used[j]) restP.push(j);
  if (restE.length && restP.length) {
    const score = (e, p) => {
      let s = 0;
      if (e.tile === p.tile) s += 3;
      if (e.last_actor === p.actor) s += 2;
      if (e.junme === p.snap.junme[target]) s += 2;
      return s > 0 ? s : -1;
    };
    const ne = restE.length;
    const np = restP.length;
    const dp = Array.from({ length: ne + 1 }, () => new Array(np + 1).fill(NEG));
    const bt = Array.from({ length: ne + 1 }, () => new Array(np + 1).fill(null));
    dp[0][0] = 0;
    for (let i = 0; i <= ne; i += 1) {
      for (let j = 0; j <= np; j += 1) {
        const v0 = dp[i][j];
        if (v0 === NEG) continue;
        if (i < ne && j < np) {
          const v = v0 + score(entries[restE[i]], points[restP[j]]);
          if (v > dp[i + 1][j + 1]) { dp[i + 1][j + 1] = v; bt[i + 1][j + 1] = ['m', i, j]; }
        }
        if (i < ne && v0 - 0.6 > dp[i + 1][j]) {
          dp[i + 1][j] = v0 - 0.6;
          bt[i + 1][j] = ['e', i, null];
        }
        if (j < np && v0 - 0.6 > dp[i][j + 1]) {
          dp[i][j + 1] = v0 - 0.6;
          bt[i][j + 1] = ['p', null, j];
        }
      }
    }
    let i = ne;
    let j = np;
    while (i > 0 || j > 0) {
      const b = bt[i][j];
      if (!b) break;
      if (b[0] === 'm') { match[restE[b[1]]] = points[restP[b[2]]]; i -= 1; j -= 1; }
      else if (b[0] === 'e') i -= 1;
      else j -= 1;
    }
  }
  return match;
}

// ---------------------------------------------------------------- 五、记账
export const CALL_TYPES = new Set(['chi', 'pon', 'daiminkan', 'ankan', 'kakan', 'none']);
// 顺序与桌面版 mr.py 的 CATS 完全一致，导出表格的列序才对得上
export const CATS = ['牌效', '防守', '副露压力下', '立直判断', '鸣牌判断', '和了', '未知'];

export function classify(entry, snap, target) {
  // 和了/见逃不是牌效决策：单独归一类，不进五项（和了本身已经由和了率/放铳率反映）。
  // 只要这一手存在「和牌」这个可选动作就算（见逃时 actual 是打牌，不判 actual 会漏）。
  const types = new Set(entry.details.map((x) => actKey(x.action).split('|')[0]));
  if (types.has('hora') || (entry.actual && entry.actual.type === 'hora')) return '和了';
  if (types.has('reach')) return '立直判断';
  if (types.size && [...types].every((t) => CALL_TYPES.has(t))) return '鸣牌判断';
  if (!snap) return '未知';
  for (let p = 0; p < 4; p += 1) if (p !== target && snap.riichi[p]) return '防守';
  for (let p = 0; p < 4; p += 1) {
    if (p === target) continue;
    if (snap.melds[p].filter((m) => m.type !== 'ankan').length >= 2) return '副露压力下';
  }
  return '牌效';
}

/** 一场每个决策的明细（含 Q 差、分类、当时的牌桌状态） */

/** 报告结构校验：缺字段 / 三麻都给出人类能看懂的报错，而不是 undefined.map 崩溃 */
export function verifyReport(report) {
  const log = report.mjai_log;
  if (!Array.isArray(log) || !log.length) throw new Error('报告里没有 mjai_log，可能下载不完整');
  if (!report.review || !Array.isArray(report.review.kyokus)) throw new Error('报告里没有 review.kyokus');
  if (typeof report.player_id !== 'number') throw new Error('报告缺少 player_id');
  const start = log.find((e) => e.type === 'start_kyoku');
  if (!start) throw new Error('报告里没有 start_kyoku');
  const n = (start.tehais || []).length;
  if (n !== 4) throw new Error(`这场是 ${n} 人麻将，当前版本只支持四麻`);
  return true;
}

export function analyze(report) {
  if (!report || typeof report !== 'object') throw new Error('报告为空或格式不对');
  verifyReport(report);
  const target = report.player_id;
  const pts = decisions(report.mjai_log, target);
  const byKy = new Map();
  for (const p of pts) {
    if (!byKy.has(p.snap.ordinal)) byKy.set(p.snap.ordinal, []);
    byKy.get(p.snap.ordinal).push(p);
  }
  const rows = [];
  report.review.kyokus.forEach((ky, kn) => {
    const entries = ky.entries;
    const plist = byKy.get(kn) || [];
    const match = alignKyoku(entries, plist, target);
    entries.forEach((e, i) => {
      const point = match[i];
      const snap = point ? point.snap : null;
      if (!e.details || !e.details.length) return;
      const exact = new Map();
      const relaxed = new Map();
      for (const x of e.details) {
        const k = actKey(x.action);
        if (!exact.has(k)) exact.set(k, x.q_value);
        const r = actKey(x.action, true);
        if (!relaxed.has(r)) relaxed.set(r, x.q_value);
      }
      const qExpected = pickQ(exact, relaxed, e.expected, e.details, 0);
      const qActual = pickQ(exact, relaxed, e.actual, e.details, e.actual_index);
      if (qActual === undefined || qExpected === undefined) return;
      rows.push({
        kyoku: kn,
        junme: e.junme,
        tile: e.tile,
        cat: classify(e, snap, target),
        diff: qExpected - qActual,
        q_actual: qActual,
        q_expected: qExpected,
        actual: e.actual,
        expected: e.expected,
        snap,
        entry: e,
        matched: !!point,
      });
    });
  });
  return rows;
}

export function summary(rows) {
  const n = rows.length;
  const s = { n };
  for (const cat of CATS) {
    const sub = rows.filter((r) => r.cat === cat);
    s[cat] = n ? (pySum(sub.map((r) => r.diff)) / n) * 100 : 0;
    s[`${cat}_n`] = sub.length;
    s[`${cat}_raw`] = pySum(sub.map((r) => r.diff));
  }
  s.loss = n ? (pySum(rows.map((r) => r.diff)) / n) * 100 : 0;
  s.severe = n ? (rows.filter((r) => r.diff >= 1).length / n) * 100 : 0;
  return s;
}

// ---------------------------------------------------------------- 六、安全度
export const LADDER = {
  0: '现物', 1: '见3字牌', 2: '见2字牌·筋1·9', 3: '生张字牌·筋2-8', 4: '无筋1·2·8·9', 5: '无筋中张3-7',
};

export function visible(snap, me = null) {
  const c = new Map();
  const add = (i) => c.set(i, (c.get(i) || 0) + 1);
  if (me !== null) for (const t of snap.tehai[me]) add(tileIndex(t));
  for (let p = 0; p < 4; p += 1) {
    // 被鸣走的牌已经算进副露里了，这里跳过，避免一张牌数两次
    for (const d of snap.kawa[p]) if (!d.called) add(tileIndex(d.pai));
    for (const m of snap.melds[p]) {
      if (m.type === 'ankan') {
        // 暗杠没有 pai，四张都在 consumed 里
        for (const t of m.consumed || []) if (t) add(tileIndex(t));
        continue;
      }
      if (m.pai) add(tileIndex(m.pai));
      for (const t of m.consumed || []) if (t) add(tileIndex(t));
    }
  }
  for (const dm of snap.dora_markers) add(tileIndex(dm));
  return c;
}

export function isGenbutsu(snap, opp, t) {
  for (const d of snap.kawa[opp]) if (tileIndex(d.pai) === t) return true;
  const rs = snap.riichi_seq[opp];
  if (rs !== null && rs !== undefined) {
    for (let p = 0; p < 4; p += 1) {
      if (p === opp) continue;
      for (const d of snap.kawa[p]) if (d.seq > rs && tileIndex(d.pai) === t) return true;
    }
  }
  return false;
}

export function safety(snap, opp, t, vis = null) {
  if (isGenbutsu(snap, opp, t)) return 0;
  const v = vis || visible(snap);
  const [s, n] = parseTile(tileName(t));
  if (s === 'z') {
    const seen = v.get(t) || 0;
    return seen >= 3 ? 1 : (seen === 2 ? 2 : 3);
  }
  const sides = [-3, 3].map((d) => n + d).filter((nn) => nn >= 1 && nn <= 9);
  const hit = sides.filter((nn) => isGenbutsu(snap, opp, tileIndex(`${nn}${s}`)));
  if (hit.length && hit.length === sides.length) return (n === 1 || n === 9) ? 2 : 3;
  return [1, 2, 8, 9].includes(n) ? 4 : 5;
}

export function worstSafety(snap, target, t) {
  const opps = [];
  for (let p = 0; p < 4; p += 1) if (snap.riichi[p] && p !== target) opps.push(p);
  if (!opps.length) return [null, ''];
  const vis = visible(snap, target);
  const g = Math.max(...opps.map((p) => safety(snap, p, t, vis)));
  return [g, LADDER[g]];
}

// ---------------------------------------------------------------- 七、压力分数
export function pressure(rows, target) {
  const bucket = { none: [0, 0, 0, 0, 0], hidden: [0, 0, 0, 0, 0], riichi: [0, 0, 0, 0, 0] };
  for (const r of rows) {
    if (r.actual.type !== 'dahai' || !r.snap) continue;
    const snap = r.snap;
    let riichi = false;
    for (let p = 0; p < snap.tehai.length; p += 1) if (p !== target && snap.riichi[p]) riichi = true;
    let tenpai = false;
    const waitAll = new Set();
    for (let p = 0; p < snap.tehai.length; p += 1) {
      if (p === target) continue;
      if (shanten(snap.tehai[p], snap.melds[p].length) === 0) {
        tenpai = true;
        const kawa = new Set(snap.kawa[p].map((x) => tileIndex(x.pai)));
        for (const w of waitingTiles(snap.tehai[p], snap.melds[p].length, kawa)) waitAll.add(w);
      }
    }
    const key = riichi ? 'riichi' : (tenpai ? 'hidden' : 'none');
    const b = bucket[key];
    b[0] += 1;
    b[1] += r.diff;
    b[4] += r.diff ** 2;
    if (waitAll.has(tileIndex(r.actual.pai))) b[2] += 1;
    if (r.expected.type === 'dahai' && waitAll.has(tileIndex(r.expected.pai))) b[3] += 1;
  }
  const out = {};
  for (const [k, v] of Object.entries(bucket)) {
    out[k] = {
      n: v[0], loss: v[1], sq: v[4], per100: v[0] ? (v[1] / v[0]) * 100 : 0, deal: v[2], m_deal: v[3],
    };
  }
  const n = out.riichi.n + out.hidden.n;
  const loss = out.riichi.loss + out.hidden.loss;
  out.merged = {
    n, loss, sq: out.riichi.sq + out.hidden.sq, per100: n ? (loss / n) * 100 : 0,
  };
  return out;
}

// ---------------------------------------------------------------- 八、牌谱自带统计
export function logStats(reportOrLog) {
  const log = reportOrLog.mjai_log || reportOrLog;
  const target = reportOrLog.player_id === undefined ? 0 : reportOrLog.player_id;
  let kyo = 0; let win = 0; let deal = 0; let riichi = 0; let meld = 0; let meldKyo = 0;
  let winPt = 0; let dealPt = 0;
  let called = false;
  let dealt = false;
  for (const e of log) {
    const t = e.type;
    if (t === 'start_kyoku') { kyo += 1; called = false; dealt = false; }
    else if (t === 'hora') {
      if (e.actor === target) { win += 1; winPt += e.deltas[target]; }
      else if (e.target === target) {
        // 双响：一炮两家，放铳局数只算 1，铳点两家相加
        dealPt -= e.deltas[target];
        if (!dealt) { dealt = true; deal += 1; }
      }
    } else if (t === 'reach' && e.actor === target) riichi += 1;
    else if (['chi', 'pon', 'daiminkan', 'ankan', 'kakan'].includes(t) && e.actor === target) {
      meld += 1;
      if (!called) { called = true; meldKyo += 1; }
    }
  }
  return {
    kyoku: kyo, win, deal, riichi, meld, meld_kyo: meldKyo,
    win_rate: kyo ? (win / kyo) * 100 : 0,
    deal_rate: kyo ? (deal / kyo) * 100 : 0,
    riichi_rate: kyo ? (riichi / kyo) * 100 : 0,
    meld_rate: kyo ? (meldKyo / kyo) * 100 : 0,
    avg_win: win ? winPt / win : 0,
    avg_deal: deal ? dealPt / deal : 0,
  };
}

export function finalScores(report) {
  let scores = [25000, 25000, 25000, 25000];
  let oya = 0;
  let kyotaku = 0; // 供托（桌上没人拿走的立直棒）
  for (const e of report.mjai_log) {
    if (e.type === 'start_kyoku') {
      scores = e.scores.map(Number); oya = e.oya;
      kyotaku = e.kyotaku || 0;                     // 起局时桌上的立直棒是权威值
    }
    else if (e.type === 'end_game' && e.scores) scores = [...e.scores];
    else if (['hora', 'ryukyoku', 'ryuukyoku', 'reach_accepted'].includes(e.type)) {
      if (e.scores) scores = e.scores.map(Number);
      else if (e.type === 'reach_accepted') { scores[e.actor] -= 1000; kyotaku += 1; }
      else {
        for (let i = 0; i < (e.deltas || []).length; i += 1) scores[i] += e.deltas[i];
        // 和了时立直棒进了和牌者的收入里；流局时留在桌上（供托继续累积）
        if (e.type === 'hora') kyotaku = 0;
      }
    }
  }
  // 终局还在桌上的供托按天凤/雀魂规则归头名；不补这一步终局总分不会是 100000
  if (kyotaku > 0) {
    let top = 0;
    for (let i = 1; i < scores.length; i += 1) if (scores[i] > scores[top]) top = i;
    scores[top] += kyotaku * 1000;
  }
  // 天凤/雀魂终局同分：按起家座次 0→1→2→3 定顺位，与末局庄家无关
  const order = scores.map((_, i) => i).sort((a, b) => (scores[b] - scores[a]) || (a - b));
  return [scores[report.player_id], order.indexOf(report.player_id) + 1];
}

// ---------------------------------------------------------------- 九、小工具
export function actCn(a) {
  const t = a.type;
  if (t === 'dahai') return `${a.tsumogiri ? '摸切' : ''}${a.pai || ''}`;
  if (t === 'none') return '过';
  const m = {
    reach: '立直', chi: '吃', pon: '碰', daiminkan: '大明杠', ankan: '暗杠', kakan: '加杠', hora: '和了',
  };
  return m[t] || String(t);
}

export function kyokuName(snap) {
  if (!snap) return '?';
  const names = {
    E: '东', S: '南', W: '西', N: '北',
  };
  return `${names[snap.bakaze] || snap.bakaze}${snap.kyoku}${snap.honba ? ` ${snap.honba}本` : ''}`;
}

/** 从天凤链接取 log id、座位、时间、卓 */
export function tenhouInfo(link) {
  if (!link) return [null, null, '', ''];
  const mq = /paipu=([0-9a-zA-Z_-]+)/.exec(link);
  if (mq && !/\d{10}gm-/.test(link)) {
    const tok = mq[1];
    const d6 = /^(\d{6})/.exec(tok);
    // 雀魂两种 paipu：251125-xxxx-… 和混淆过的 jmjnt-…
    return [tok, null, d6 ? `20${d6[1].slice(0, 2)}-${d6[1].slice(2, 4)}-${d6[1].slice(4, 6)}` : '', '雀魂'];
  }
  const mm = /(\d{10}gm-([0-9a-f]{4})-\d{4}-[0-9a-f]{8})/.exec(link);
  const log = mm ? mm[1] : null;
  const tw = /tw=(\d)/.exec(link);
  const when = log ? `${log.slice(0, 4)}-${log.slice(4, 6)}-${log.slice(6, 8)} ${log.slice(8, 10)}时` : '';
  // 天凤房间码：第 3 位是卓别，末位 9=四麻、1=三麻（东风战）
  const ROOM = { 0: '一般', 8: '上级', a: '特上', e: '凤凰' };
  let lobby = '';
  if (mm) {
    lobby = ROOM[mm[2][2]] || mm[2];
    if (mm[2][3] === '1') lobby += '东风';
  }
  return [log, tw ? parseInt(tw[1], 10) : null, when, lobby];
}

// 报告里嵌着原始天凤牌谱的头信息（split_logs[0].rule.disp），头一个字就是卓
export const LOBBY_NAMES = {
  般: '一般', 上: '上级', 特: '特上', 鳳: '凤凰', 凤: '凤凰', 雀: '雀魂',
};

/** 从报告里挖出卓、同桌玩家名。rule.disp 例如「上南喰赤」。 */
export function reportMeta(report) {
  const out = { lobby: '', players: [] };
  for (const blk of report.split_logs || []) {
    if (!blk || typeof blk !== 'object') continue;
    const disp = String((blk.rule || {}).disp || '');
    if (disp) out.lobby = LOBBY_NAMES[disp[0]] || '';
    const names = blk.name || [];
    if (names.length) out.players = names.map(String);
    break;
  }
  return out;
}

/** 没给牌谱链接时，用当前时间当日期，格式统一 YYYY-MM-DD HH时 */
export function nowStamp(d = new Date()) {
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}时`;
}

export { HONORS };
