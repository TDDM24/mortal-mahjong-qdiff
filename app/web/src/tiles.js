// 牌的工具函数：和 mr.py 的 tile_index / tile_name / parse_tile / dora_from_indicator 一一对应
export const HONORS = ['E', 'S', 'W', 'N', 'P', 'F', 'C'];
export const SUITS = 'mps';

/** '5mr' → 0..33 的整数（和 Python 的 tile_index 完全一致） */
export function tileIndex(t) {
  if (!t || t === '?') return -1; // 单视角牌谱里的未知暗牌
  const s = t.replace(/r/g, '');
  const h = HONORS.indexOf(s);
  if (h >= 0) return 27 + h;
  const suit = s[s.length - 1];
  const num = parseInt(s.slice(0, -1), 10);
  return { m: 0, p: 9, s: 18 }[suit] + num - 1;
}

export function tileName(i) {
  if (i >= 27) return HONORS[i - 27];
  return `${(i % 9) + 1}${SUITS[Math.floor(i / 9)]}`;
}

/** '5mr' → ['m', 5]；'E' → ['z', 1] */
export function parseTile(t) {
  const s = t.replace(/r/g, '');
  const h = HONORS.indexOf(s);
  if (h >= 0) return ['z', h + 1];
  return [s[s.length - 1], parseInt(s.slice(0, -1), 10)];
}

export function doraFromIndicator(ind) {
  const [s, n] = parseTile(ind);
  if (s === 'z') {
    const m = { 1: 2, 2: 3, 3: 4, 4: 1, 5: 6, 6: 7, 7: 5 };
    return HONORS[m[n] - 1];
  }
  return `${n < 9 ? n + 1 : 1}${s}`;
}

export function isHonor(t) {
  return HONORS.includes(t.replace(/r/g, ''));
}

export function isTerminal(t) {
  const [s, n] = parseTile(t);
  return s === 'z' || n === 1 || n === 9;
}

/** Python 的 sum() 从左到右累加，浮点结果依赖顺序；这里保证顺序一致 */
export function pySum(xs) {
  let s = 0;
  for (const x of xs) s += x;
  return s;
}
