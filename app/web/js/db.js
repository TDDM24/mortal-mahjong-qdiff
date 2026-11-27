// IndexedDB 存储：一场一条记录（含报告原文 JSON），按 seq 递增，rid 唯一。
// 为什么不用 Capacitor SQLite：这个是纯网页就能测的方案，没有原生插件；单场 JSON 300–400 KB，
// 结构化克隆存得下；再配合 navigator.storage.persist() 和「导出/导入」做备份。
const DB_NAME = 'mahjong';
const DB_VER = 1;

// 调试用：?mem=1 时全部放内存（headless 浏览器里 IndexedDB 起不来，截图和自动化测试要用它）。
// 正常打开不会走这条路，数据仍然在 IndexedDB 里。
const MEM = typeof location !== 'undefined'
  && new URLSearchParams(location.search).get('mem') === '1';
const memGames = new Map();
const memKV = new Map();

let _db = null;

function openDB() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VER);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains('games')) {
        const s = db.createObjectStore('games', { keyPath: 'seq' });
        s.createIndex('rid', 'rid', { unique: true });
        s.createIndex('key', 'key');
      }
      if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv', { keyPath: 'k' });
    };
    req.onsuccess = () => { _db = req.result; resolve(_db); };
    req.onerror = () => reject(req.error);
  });
}

function tx(store, mode, fn) {
  return openDB().then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const s = t.objectStore(store);
    let out;
    try { out = fn(s); } catch (e) { reject(e); return; }
    t.oncomplete = () => resolve(out && out.result !== undefined ? out.result : out);
    t.onerror = () => reject(t.error);
    t.onabort = () => reject(t.error);
  }));
}

const req2p = (r) => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });

export async function addGame(rec) {
  if (MEM) {
    for (const g of memGames.values()) {
      if (g.rid !== rec.rid) continue;
      // 旧记录缺报告原文时补上，否则详情/重算/审计都读不到
      if (!g.report && rec.report) {
        memGames.set(g.seq, { ...g, ...rec, seq: g.seq });
        return { seq: g.seq, existed: true, repaired: true };
      }
      return { seq: g.seq, existed: true };
    }
    const seq = memGames.size ? Math.max(...memGames.keys()) + 1 : 1;
    memGames.set(seq, { ...rec, seq });
    return { seq, existed: false };
  }
  const db = await openDB();
  const t = db.transaction('games', 'readwrite');
  const s = t.objectStore('games');
  const exists = await req2p(s.index('rid').get(rec.rid));
  if (exists) {
    if (!exists.report && rec.report) {
      s.put({ ...exists, ...rec, seq: exists.seq });
      await new Promise((res, rej) => { t.oncomplete = res; t.onerror = () => rej(t.error); });
      return { seq: exists.seq, existed: true, repaired: true };
    }
    t.abort();
    return { seq: exists.seq, existed: true };
  }
  const all = await req2p(s.getAllKeys());
  const seq = all.length ? Math.max(...all) + 1 : 1;
  const row = { ...rec, seq };
  s.put(row);
  await new Promise((res, rej) => { t.oncomplete = res; t.onerror = () => rej(t.error); });
  return { seq, existed: false };
}

export async function putGame(rec) {
  if (MEM) { memGames.set(Number(rec.seq), rec); return; }
  const db = await openDB();
  return tx('games', 'readwrite', (s) => s.put(rec));
}

export async function allGames() {
  if (MEM) return [...memGames.values()].sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.seq - b.seq));
  const db = await openDB();
  const rows = await req2p(db.transaction('games').objectStore('games').getAll());
  return rows.sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.seq - b.seq));
}

/**
 * 只读汇总行、不带报告原文（列表页/筛选器用）。
 * 报告原文单场几百 KB，全部读进内存是 1.0.x 卡顿和 OOM 的主因，
 * 详情页和审计页各自按 seq 现取。
 */
export async function allMeta() {
  const list = await allGames();
  return list.map((rec) => {
    const { report, ...meta } = rec;
    return meta;
  });
}

export async function getGame(seq) {
  if (MEM) return memGames.get(Number(seq)) || null;
  const db = await openDB();
  return req2p(db.transaction('games').objectStore('games').get(Number(seq)));
}

export async function deleteGame(seq) {
  if (MEM) { memGames.delete(Number(seq)); return; }
  const db = await openDB();
  return tx('games', 'readwrite', (s) => s.delete(Number(seq)));
}

export async function count() {
  if (MEM) return memGames.size;
  const db = await openDB();
  return req2p(db.transaction('games').objectStore('games').count());
}

export async function clearAll() {
  if (MEM) { memGames.clear(); memKV.delete('calc_version'); return; }
  const db = await openDB();
  await tx('games', 'readwrite', (s) => s.clear());
  // 口径标记跟着数据一起清，否则清空后仍显示旧版本口径
  return tx('kv', 'readwrite', (s) => s.delete('calc_version'));
}

export async function getKV(k, dflt) {
  if (MEM) return memKV.has(k) ? memKV.get(k) : dflt;
  const db = await openDB();
  const r = await req2p(db.transaction('kv').objectStore('kv').get(k));
  return r ? r.v : dflt;
}

export async function setKV(k, v) {
  if (MEM) { memKV.set(k, v); return; }
  const db = await openDB();
  return tx('kv', 'readwrite', (s) => s.put({ k, v }));
}

export async function estimate() {
  try {
    const e = await navigator.storage.estimate();
    return { usage: e.usage || 0, quota: e.quota || 0 };
  } catch { return { usage: 0, quota: 0 }; }
}

export async function persist() {
  try { return await navigator.storage.persist(); } catch { return false; }
}
