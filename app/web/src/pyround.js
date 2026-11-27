// Python 的 round() 是「四舍六入五成双」（banker's rounding），而且是对二进制精确值取整；
// JS 的 Math.round / toFixed 是五入。这里的实现先把这个 double 拆成"整数 × 2^e"的精确形式，
// 再用 BigInt 做五成双，结果和 Python round(x, nd) 逐位一致。
const F64 = new DataView(new ArrayBuffer(8));

export function pyRound(x, nd = 0) {
  if (!Number.isFinite(x) || x === 0) return x;
  const sign = x < 0 ? -1 : 1;
  const a = Math.abs(x);
  F64.setFloat64(0, a);
  const hi = F64.getUint32(0);
  const lo = F64.getUint32(4);
  const eField = (hi >>> 20) & 0x7ff;
  let mant = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
  let e;
  if (eField === 0) {
    e = -1074;
  } else {
    mant |= 1n << 52n;
    e = eField - 1075;
  }
  // a = mant × 2^e ；a × 10^nd = mant × 5^nd × 2^(e+nd)
  const pow5 = 5n ** BigInt(nd);
  const N = mant * pow5;
  const k = e + nd;
  let q;
  if (k >= 0) {
    q = N << BigInt(k);
  } else {
    const shift = BigInt(-k);
    q = N >> shift;
    const rem = N - (q << shift);
    const half = 1n << (shift - 1n);
    if (rem > half) q += 1n;
    else if (rem === half) q += q & 1n;   // 正好一半：向偶数取整
  }
  const scale = 10 ** nd;
  return (sign * Number(q)) / scale;
}

/** 递归把对象里所有数字按 nd 位四舍五入（golden 文件就是 4 位） */
export function roundDeep(o, nd = 4) {
  if (typeof o === 'number') return Number.isInteger(o) ? o : pyRound(o, nd);
  if (Array.isArray(o)) return o.map((v) => roundDeep(v, nd));
  if (o && typeof o === 'object') {
    const r = {};
    for (const [k, v] of Object.entries(o)) r[k] = roundDeep(v, nd);
    return r;
  }
  return o;
}
