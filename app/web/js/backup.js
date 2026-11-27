// 备份的打包/解包：紧凑 JSON + gzip。
// 单场 728 KB（缩进）→ 332 KB（紧凑）→ 39 KB（gzip），省 95%，手机上存/传都轻松。
// 兼容旧备份：解包时先看 gzip 魔数，不是就当普通 JSON 文本读。

const GZIP_MAGIC = [0x1f, 0x8b];

export function isGzip(buf) {
  const u = new Uint8Array(buf);
  return u.length > 2 && u[0] === GZIP_MAGIC[0] && u[1] === GZIP_MAGIC[1];
}

export const gzipSupported = () => typeof CompressionStream === 'function';

/** 字符串 → gzip 字节（不支持 CompressionStream 时返回 null） */
export async function gzipText(text) {
  if (!gzipSupported()) return null;
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'));
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf);
}

/** gzip 字节 → 字符串 */
export async function gunzipBytes(bytes, maxBytes = 256 * 1024 * 1024) {
  // 解压上限：防止把 40 KB 的 gzip 炸弹解成几个 G 把 WebView 撑爆
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  const reader = stream.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > maxBytes) {
      await reader.cancel().catch(() => {});
      throw new Error(`备份解压后超过 ${Math.round(maxBytes / 1048576)} MB，已中止（可能不是备份文件）`);
    }
    chunks.push(value);
  }
  const all = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) { all.set(c, off); off += c.length; }
  return new TextDecoder('utf-8').decode(all);
}

/** Uint8Array → base64（分块拼，避免大数组一次 btoa 卡住） */
export function toBase64(bytes) {
  const CH = 0x8000;
  let s = '';
  for (let i = 0; i < bytes.length; i += CH) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
  }
  return btoa(s);
}

/** 打包成要写出去的东西：{ base64, mime, ext, sizeKB, compressed } */
export async function packBackup(payload) {
  const text = JSON.stringify(payload);          // 紧凑，无缩进
  const gz = await gzipText(text);
  if (gz) {
    return {
      base64: toBase64(gz), mime: 'application/gzip', ext: '.json.gz',
      sizeKB: Math.round(gz.length / 1024), compressed: true, rawKB: Math.round(text.length / 1024),
    };
  }
  return {
    text, mime: 'application/json', ext: '.json',
    sizeKB: Math.round(new Blob([text]).size / 1024), compressed: false, rawKB: Math.round(new Blob([text]).size / 1024),
  };
}

/** 把读到的文件内容还原成对象。buf 可以是 ArrayBuffer / Uint8Array；也接受纯文本（旧代码路径） */
export async function unpackBackup(buf) {
  let text;
  if (typeof buf === 'string') {
    text = buf;
  } else if (isGzip(buf)) {
    text = await gunzipBytes(new Uint8Array(buf));
  } else {
    text = new TextDecoder('utf-8').decode(new Uint8Array(buf));
  }
  const obj = JSON.parse(text);
  if (Array.isArray(obj)) return { games: obj };
  return obj;
}
