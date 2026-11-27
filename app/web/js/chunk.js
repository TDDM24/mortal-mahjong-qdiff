/** 把长字符串切成小块（按 UTF-16 长度），并且不把代理对（emoji 等）切成两半 */
export function splitChunks(text, size = 32768) {
  const out = [];
  let i = 0;
  while (i < text.length) {
    let j = Math.min(i + size, text.length);
    if (j < text.length) {
      const code = text.charCodeAt(j - 1);
      if (code >= 0xD800 && code <= 0xDBFF) j += 1;   // 高代理，往后挪一位
    }
    out.push(text.slice(i, j));
    i = j;
  }
  return out;
}
