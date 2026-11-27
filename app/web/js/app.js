// 手机界面：记录 / 列表 / 详情 / 审计 / 设置。计算全在 ../src/（第 1 阶段那套，未改动）。
import { compute } from '../src/core.js';
import * as R from '../src/render.js';
import * as mr from '../src/mr.js';
import * as effaudit from '../src/effaudit.js';
import { auditView } from './auditview.js';
import { detailHtml } from './detailview.js';
import { splitChunks } from './chunk.js';
import { packBackup, unpackBackup, toBase64 } from './backup.js';
import { METRICS, dateParts, hourLabel, metricBounds, filteredGames, groupByDate, usableCount } from './listfilter.js';
import * as db from './db.js';
import * as rows from './rows.js';
import { extractRid, fetchReport, pickJsonFile, pickFileBuffer } from './net.js';

const VERSION = 'v1.0.0';
const view = document.getElementById('view');
const titleEl = document.getElementById('title');
const backEl = document.getElementById('back');
const tabsEl = document.getElementById('tabs');
const toastEl = document.getElementById('toast');

const S = {
  settings: { theme: 'system', lines: null, linesOn: false },
  games: [],
  calcVersion: '',
  busy: false,
};

// ---------------------------------------------------------------- 小工具
const esc = (s) => String(s === null || s === undefined ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

let toastTimer = null;
function toast(msg, ms = 2400) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.hidden = true; }, ms);
}

/** 日志：写到应用私有目录（native 侧），设置页可以导出来。浏览器里只打 console */
function logline(msg) {
  const line = `${new Date().toISOString().slice(0, 19).replace('T', ' ')} ${msg}`;
  try { console.log(line); } catch { /* 忽略 */ }
  const cap = window.Capacitor;
  if (cap && typeof cap.nativePromise === 'function') {
    cap.nativePromise('FileSaver', 'log', { line }).catch(() => {});
  }
}

/** 保存文件：安卓上弹系统「保存到…」，分块写；浏览器里退回下载。
 *  分块是为了不让几百 KB 的字符串一次跨桥——以前那样会在选完文件回到应用时崩。 */
async function saveFile(name, text, mime = 'application/json') {
  if (window.MJ_MAC) {
    return saveViaMac(name, toBase64(new TextEncoder().encode(text)), mime);
  }
  const cap = window.Capacitor;
  const kb = Math.round(new Blob([text]).size / 1024);
  logline(`导出开始：${name}（${kb} KB，${mime}）`);
  if (cap && typeof cap.nativePromise === 'function') {
    const token = `t${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
    try {
      await cap.nativePromise('FileSaver', 'open', { token, fileName: name, mime });
      logline('用户已选位置，开始分块写入');
      const chunks = splitChunks(text, 32768);
      for (const part of chunks) {
        await cap.nativePromise('FileSaver', 'write', { token, data: part });
      }
      await cap.nativePromise('FileSaver', 'close', { token });
      logline(`导出完成：${chunks.length} 块`);
      toast('已保存');
      return;
    } catch (e) {
      const msg = String((e && e.message) || e);
      logline(`导出失败：${msg}`);
      // 中途失败必须把原生侧的流关掉，否则句柄一直挂着
      try { await cap.nativePromise('FileSaver', 'close', { token }); } catch (_) { /* 已关 */ }
      if (/cancel/i.test(msg)) return;               // 用户自己取消
      toast(`保存失败：${msg}，改用下载`);
    }
  } else {
    logline('没有原生插件，走浏览器下载');
  }
  download(name, text, mime);
}

/** 保存二进制：base64 按 4 的倍数切块，原生侧逐块解码后写入 */
async function saveFileBinary(name, base64, mime = 'application/octet-stream') {
  if (window.MJ_MAC) {
    return saveViaMac(name, base64, mime);
  }
  const cap = window.Capacitor;
  const kb = Math.round((base64.length * 3) / 4 / 1024);
  logline(`导出（二进制）开始：${name}（约 ${kb} KB，${mime}）`);
  if (cap && typeof cap.nativePromise === 'function') {
    const token = `t${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
    try {
      await cap.nativePromise('FileSaver', 'open', { token, fileName: name, mime });
      logline('用户已选位置，开始分块写入（base64）');
      const CH = 32768;                       // 32768 % 4 === 0
      let i = 0;
      let blocks = 0;
      while (i < base64.length) {
        const part = base64.slice(i, i + CH);
        await cap.nativePromise('FileSaver', 'write', { token, data: part, base64: true });
        i += CH;
        blocks += 1;
      }
      await cap.nativePromise('FileSaver', 'close', { token });
      logline(`导出（二进制）完成：${blocks} 块`);
      toast('已保存');
      return;
    } catch (e) {
      const msg = String((e && e.message) || e);
      logline(`导出（二进制）失败：${msg}`);
      try { await cap.nativePromise('FileSaver', 'close', { token }); } catch (_) { /* 已关 */ }
      if (/cancel/i.test(msg)) return;
      toast(`保存失败：${msg}`);
      return;
    }
  }
  // 浏览器：直接下载
  const bin = atob(base64);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) u8[i] = bin.charCodeAt(i);
  const blob = new Blob([u8], { type: mime });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

/** Mac 壳：交给原生弹「存储为…」，用户在哪儿存、叫什么名字自己定 */
async function saveViaMac(name, base64, mime) {
  const kb = Math.round((base64.length * 3) / 4 / 1024);
  logline(`Mac 保存开始：${name}（约 ${kb} KB）`);
  try {
    const r = await fetch('/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, mime, base64 }),
    });
    const j = await r.json();
    if (j.ok) { logline(`Mac 保存完成：${j.path}`); toast('已保存'); return; }
    if (j.cancelled) { logline('Mac 保存：用户取消'); return; }
    logline(`Mac 保存失败：${j.error}`);
    toast(`保存失败：${j.error}`);
  } catch (e) {
    logline(`Mac 保存异常：${e.message}`);
    toast(`保存失败：${e.message}`);
  }
}

/** 把调试日志导出成一个 txt（同样走系统保存对话框，日志很小） */
// 修复计算口径后，把旧记录按当前版本重算一遍（库里存了报告原文，所以能重算）
async function recalcAll() {
  const btn = document.getElementById('btnRecalc');
  const info = document.getElementById('recalcInfo');
  const games = await db.allMeta();
  if (!games.length) { toast('还没有记录'); return; }
  if (btn) btn.disabled = true;
  let done = 0;
  let changed = 0;
  let failed = 0;
  for (const rec of games) {
    done += 1;
    if (btn) btn.textContent = `重算中 ${done}/${games.length}`;
    // 原文按需读，一进一出，不会把整库报告同时留在内存里
    const full = await db.getGame(rec.seq);
    if (!full || !full.report) { failed += 1; continue; }
    try {
      const g = buildG(full.rid, full.report);
      const old = rec.row || {};
      const row = rows.buildRow(g, '', '', old['序号'] ?? null);
      // 这几列是人工录入的，重算时原样保留
      for (const k of ['序号', '日期', '备注', '天凤牌谱', 'tw']) {
        if (k in old) row[k] = old[k];
      }
      if (old['合计失分'] !== row['合计失分'] || old['严重失误'] !== row['严重失误']) changed += 1;
      // 注意：rec 来自 allMeta()，里面没有 report；写回必须用 full，否则原文被抹掉
      await db.putGame({
        ...full, row, rank: g.rank, rating: g.rating, score: g.score,
        zhuo: row['卓'], date: row['日期'], calcVersion: VERSION,
      });
    } catch (e) {
      failed += 1;
      logline(`重算失败 ${rec.rid}: ${e.message}`);
    }
    if (done % 4 === 0) await new Promise((r) => setTimeout(r, 0));
  }
  await db.setKV('calc_version', VERSION);
  S.calcVersion = VERSION;
  S.games = await db.allMeta();
  if (btn) { btn.disabled = false; btn.textContent = '按当前口径重算全部'; }
  const line = `重算完：${games.length} 场，其中 ${changed} 场的失分或有变化，${failed} 场失败。`;
  if (info) info.textContent = line;
  toast(`重算完，${changed} 场有变化`);
}

async function exportDebugLog() {
  const cap = window.Capacitor;
  let text = `麻将记录 ${VERSION}\n（没有原生插件，没有原生日志）\n`;
  if (cap && typeof cap.nativePromise === 'function') {
    try {
      const r = await cap.nativePromise('FileSaver', 'readLog', {});
      text = `麻将记录 ${VERSION}\n---- 原生日志 ${r.path || ''} ----\n${r.log || '（空）'}\n`;
    } catch (e) {
      text += `读日志失败：${e}`;
    }
  }
  await saveFile(`麻将记录日志_${stamp().replace(/[: ]/g, '')}.txt`, text, 'text/plain');
}

function download(name, text, type = 'application/json') {
  const blob = new Blob([text], { type: `${type};charset=utf-8` });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

const pad = (n) => String(n).padStart(2, '0');
function stamp() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}时`;
}

function applyTheme() {
  const t = S.settings.theme || 'system';
  const dark = t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  const meta = document.querySelector('meta[name=theme-color]');
  if (meta) meta.setAttribute('content', dark ? '#1c1a17' : '#f7f3ea');
}

function applyLines() {
  const ls = S.settings.lines;
  if (Array.isArray(ls) && ls.length === 5) R.setLines(ls, !!S.settings.linesOn);
  else R.setLines(R.DEFAULT_LINES, false);
}

async function saveSettings() {
  await db.setKV('settings', S.settings);
  applyTheme();
  applyLines();
}

/** 由报告算出界面要用的 g（compute 返回的是超集，够用） */
function buildG(rid, report) {
  const g = compute(rid, report, {});
  if (!g.lobby) g.lobby = mr.reportMeta(report).lobby || '';
  return g;
}

function fiveTable(g) {
  const cell = (name, value, note) => {
    const st = R.lineState(name, value);
    const cls = st ? `v ${st}` : 'v';
    const n = note ? `<small>（${esc(note)}）</small>` : '';
    return `<tr><td class="k">${esc(name)}</td><td class="${cls}">${R.fmt5(name, value)}${n}</td></tr>`;
  };
  return `<table class="five">${g.five.map((f) => cell(f.name, f.value, f.note)).join('')}</table>`;
}

// ---------------------------------------------------------------- 记录
function renderRecord() {
  titleEl.textContent = '记录';
  backEl.hidden = true;
  view.innerHTML = `
    <div class="card">
      <label class="f"><span>报告链接或 16 位 id（killerducky 链接也认）</span>
        <textarea id="ridInput" placeholder="https://mjai.ekyu.moe/#/report/0b0d6c2336b144eb&#10;或直接粘贴 0b0d6c2336b144eb"></textarea>
      </label>
      <label class="f"><span>天凤牌谱链接（可选，用来取日期和卓）</span>
        <input type="text" id="linkInput" placeholder="http://tenhou.net/0/?log=2026112521gm-0089-0000-xxxxxxxx&tw=2">
      </label>
      <label class="f"><span>备注（可选）</span>
        <input type="text" id="noteInput" placeholder="例如：上级卓第一场">
      </label>
      <div class="row">
        <button id="btnRecord">取报告并记录</button>
        <button class="ghost" id="btnOnly">只看数字</button>
      </div>
      <p class="hint">「记录」会把报告原文一起存进手机（网站上的报告 15 天后会过期，存下来才能以后再看）。</p>
      <p class="hint">浏览器里读不到 mjai.ekyu.moe（CORS），可以用 <button class="ghost" id="btnImport" style="padding:4px 10px">导入报告 JSON</button> 代替。</p>
    </div>
    <div id="result"></div>`;
  document.getElementById('btnRecord').onclick = () => doFetch(true);
  document.getElementById('btnOnly').onclick = () => doFetch(false);
  document.getElementById('btnImport').onclick = () => doImportReport();
}

async function doFetch(save) {
  if (S.busy) return;
  const rid = extractRid(document.getElementById('ridInput').value);
  const link = document.getElementById('linkInput').value.trim();
  const note = document.getElementById('noteInput').value.trim();
  const box = document.getElementById('result');
  if (!rid) { toast('没看懂报告 id：应该是 16 位十六进制'); return; }
  S.busy = true;
  box.innerHTML = '<div class="card"><p class="hint" id="prog">正在取报告…</p></div>';
  const r = await fetchReport(rid, (m) => { const p = document.getElementById('prog'); if (p) p.textContent = m; });
  S.busy = false;
  if (!r.ok) {
    box.innerHTML = `<div class="card"><p class="err">${esc(r.message)}</p></div>`;
    return;
  }
  await showResult(rid, r.data, link, note, save);
}

async function doImportReport() {
  const f = await pickJsonFile();
  if (!f) return;
  const box = document.getElementById('result');
  if (f.error) { box.innerHTML = `<div class="card"><p class="err">${esc(f.error)}</p></div>`; return; }
  const rid = extractRid(f.name) || extractRid((f.data && f.data.ref) || '');
  if (!rid) { toast('文件名里没有 16 位报告 id'); return; }
  await showResult(rid, f.data, document.getElementById('linkInput').value.trim(),
    document.getElementById('noteInput').value.trim(), true);
}

async function showResult(rid, report, link, note, save) {
  const box = document.getElementById('result');
  try {
    const g = buildG(rid, report);
    if (save) {
      const row = rows.buildRow(g, link, note, null);
      const rec = {
        rid,
        key: rows.timeKey(row['天凤牌谱'], row['日期'], 0),
        date: row['日期'],
        zhuo: row['卓'],
        rank: g.rank,
        rating: g.rating,
        score: g.score,
        row,
        report,
        createdAt: new Date().toISOString(),
      };
      rec.calcVersion = VERSION;
      const res = await db.addGame(rec);
      await db.setKV('calc_version', VERSION);
      S.calcVersion = VERSION;
      logline(`记录一场 ${rid}：${res.existed ? '已存在' : `序号 ${res.seq}`}${res.repaired ? '（补上了原文）' : ''}`);
      await db.persist();
      S.games = await db.allMeta();
      const savedMsg = res.existed ? (res.repaired ? '这一场之前缺报告原文，已经补上' : '这一场之前已经记过') : `已记录，第 ${res.seq} 场`;
      toast(savedMsg);
      box.innerHTML = `<div class="card">
        <p class="ok">${savedMsg}</p>
        <div class="lead"><b class="rating">${R.fixed(g.rating, 1)}</b><span class="rating-label">Rating</span><span class="dim">${g.n_decisions} 手</span></div>
        <div class="h1">第 ${Number(g.rank)} 位　${Number(g.score)} 点${g.lobby ? `　${esc(g.lobby)}卓` : ''}</div>
        <div class="rid" data-rid="${esc(g.rid)}">报告 ${esc(g.rid)}</div>
        ${fiveTable(g)}
      </div>`;
    } else {
      box.innerHTML = `<div class="card">
        <p class="hint">只看数字，没有保存</p>
        <div class="lead"><b class="rating">${R.fixed(g.rating, 1)}</b><span class="rating-label">Rating</span><span class="dim">${g.n_decisions} 手</span></div>
        <div class="h1">第 ${Number(g.rank)} 位　${Number(g.score)} 点${g.lobby ? `　${esc(g.lobby)}卓` : ''}</div>
        <div class="rid" data-rid="${esc(g.rid)}">报告 ${esc(g.rid)}</div>
        ${fiveTable(g)}
      </div>`;
    }
  } catch (e) {
    box.innerHTML = `<div class="card"><p class="err">算不出来：${esc(e.message)}</p></div>`;
  }
}

// ---------------------------------------------------------------- 列表
const F = { open: false, from: '', to: '', lo: {}, hi: {} };

function renderList() {
  titleEl.textContent = '列表';
  backEl.hidden = true;
  if (!S.games.length) {
    view.innerHTML = '<div class="card empty"><p>还没有结果</p><p>去「记录」页粘牌谱 → 复盘 → 记录</p></div>';
    return;
  }
  const usable = usableCount(S.games);
  const bounds = metricBounds(S.games);
  const hasAnyMetric = METRICS.some(([, k]) => bounds[k]);
  if (!usable || !hasAnyMetric) {
    view.innerHTML = `<div class="card"><p class="hint">库里有 ${S.games.length} 条记录，但都没有可用的指标数据。</p>
      <p class="hint">可能是早期只有 Excel 行、没有报告原文的那种记录；也可能是报告在网站上过期且本地没存原件。
      重新用「记录」页取一次报告就能恢复这一场。</p></div>`;
    return;
  }
  const list = filteredGames(S.games, F);
  const dates = S.games.map((g) => dateParts(g.date)).filter(Boolean).sort();
  const active = (F.from || F.to || METRICS.some(([, k]) => (F.lo[k] ?? '') !== '' || (F.hi[k] ?? '') !== ''));

  const rowsHtml = METRICS.map(([label, key]) => {
    const b = bounds[key];
    if (!b) {
      return `<div class="fmetric">
        <div class="fmlabel">${label}<span class="frange">库里没有这一项的数据</span></div>
      </div>`;
    }
    const [mn, mx] = b;
    return `<div class="fmetric">
      <div class="fmlabel">${label}<span class="frange">${mn === mx ? `库里只有 ${R.fixed(mn, 2)}` : `库里这几场 ${R.fixed(mn, 2)}–${R.fixed(mx, 2)}`}</span></div>
      <div class="finputs">
        <input type="number" data-lo="${key}" value="${F.lo[key] ?? ''}" placeholder="${R.fixed(mn, 2)}" min="${mn}" max="${mx}" step="0.1">
        <span class="fdash">–</span>
        <input type="number" data-hi="${key}" value="${F.hi[key] ?? ''}" placeholder="${R.fixed(mx, 2)}" min="${mn}" max="${mx}" step="0.1">
      </div>
    </div>`;
  }).join('');

  const panel = `<div class="fpanel" id="fpanel" ${F.open ? '' : 'hidden'}>
      <div class="frow">
        <span class="fk">日期</span>
        <input type="date" id="dfrom" value="${F.from}" ${dates.length ? `min="${dates[0]}" max="${dates[dates.length - 1]}"` : ''}>
        <span class="fdash">–</span>
        <input type="date" id="dto" value="${F.to}" ${dates.length ? `min="${dates[0]}" max="${dates[dates.length - 1]}"` : ''}>
      </div>
      <p class="hint" style="margin:2px 0 6px">日期两端都填同一天就是只看那一天。${dates.length ? `已有数据：${dates[0]} ～ ${dates[dates.length - 1]}` : ''}</p>
      ${rowsHtml}
      <p class="hint" style="margin:8px 0 0">空着表示不限；标题右边的灰字是库里已记录场次的实际范围。日期两端填同一天就是只看那一天。</p>
      <button class="ghost" id="freset" style="margin-top:10px">清空筛选</button>
    </div>`;

  const body = groupByDate([...list].reverse()).map(([day, gs]) => `
    <div class="dgroup">
      <div class="dhead">${day}<span>${gs.length} 场</span></div>
      ${gs.map((g) => `
        <div class="game-item" data-seq="${g.seq}">
          <span class="no">${g.seq}</span>
          <span class="date">${hourLabel(g.date) || ''}${g.zhuo ? `<span class="pill">${esc(g.zhuo)}</span>` : ''}
            <div class="meta">第 ${Number(g.rank)} 位 · ${esc(R.fixed(g.rating, 1))} 分</div></span>
          <span class="loss">${R.fixed(g.row['合计失分'], 2)}</span>
        </div>`).join('')}
    </div>`).join('') || '<div class="dgroup"><p class="hint">没有符合条件的场次。</p></div>';

  view.innerHTML = `
    <div class="card fcard">
      <div class="fhead">
        <button class="ghost" id="ftoggle" style="padding:6px 12px">${F.open ? '收起筛选' : '筛选'}${active ? ' ·已开' : ''}</button>
        <span class="fcount">${list.length} / ${S.games.length} 场</span>
      </div>
      ${panel}
    </div>
    <div class="card">${body}</div>
    <p class="hint">数字是每 100 手失分。点一行看详情。</p>`;

  const toggle = document.getElementById('ftoggle');
  toggle.onclick = () => { F.open = !F.open; renderList(); };
  const bindNum = (sel, target, isLo) => {
    view.querySelectorAll(sel).forEach((inp) => {
      inp.oninput = () => {
        const k = inp.dataset[isLo ? 'lo' : 'hi'];
        target[k] = inp.value;
        // 只刷新列表部分，不重建输入框（否则输入焦点会跳）
        refreshListBody();
      };
    });
  };
  bindNum('input[data-lo]', F.lo, true);
  bindNum('input[data-hi]', F.hi, false);
  const dfrom = document.getElementById('dfrom');
  const dto = document.getElementById('dto');
  if (dfrom) dfrom.onchange = () => { F.from = dfrom.value; refreshListBody(); };
  if (dto) dto.onchange = () => { F.to = dto.value; refreshListBody(); };
  const reset = document.getElementById('freset');
  if (reset) reset.onclick = () => {
    F.from = ''; F.to = ''; F.lo = {}; F.hi = {};
    document.querySelectorAll('input[data-lo], input[data-hi]').forEach((el) => { el.value = ''; });
    const a = document.getElementById('dfrom'); if (a) a.value = '';
    const b = document.getElementById('dto'); if (b) b.value = '';
    refreshListBody();
  };
  bindItems();
}

/** 只重画「分组列表 + 计数」，不动筛选面板（避免输入时失焦） */
function refreshListBody() {
  const bounds = metricBounds(S.games);
  const list = filteredGames(S.games, F);
  const cnt = view.querySelector('.fcount');
  if (cnt) cnt.textContent = `${list.length} / ${S.games.length} 场`;
  const card = view.querySelectorAll('.card')[1];
  if (!card) return;
  card.innerHTML = groupByDate([...list].reverse()).map(([day, gs]) => `
    <div class="dgroup">
      <div class="dhead">${day}<span>${gs.length} 场</span></div>
      ${gs.map((g) => `
        <div class="game-item" data-seq="${g.seq}">
          <span class="no">${g.seq}</span>
          <span class="date">${hourLabel(g.date) || ''}${g.zhuo ? `<span class="pill">${esc(g.zhuo)}</span>` : ''}
            <div class="meta">第 ${Number(g.rank)} 位 · ${esc(R.fixed(g.rating, 1))} 分</div></span>
          <span class="loss">${R.fixed(g.row['合计失分'], 2)}</span>
        </div>`).join('')}
    </div>`).join('') || '<div class="dgroup"><p class="hint">没有符合条件的场次。</p></div>';
  bindItems();
}

function bindItems() {
  view.querySelectorAll('.game-item').forEach((el) => {
    el.onclick = () => { location.hash = `#/game/${el.dataset.seq}`; };
  });
}

// ---------------------------------------------------------------- 详情
async function renderGame(seq) {
  const rec = await db.getGame(seq);
  if (!rec) { view.innerHTML = '<div class="card"><p class="err">找不到这一场。</p></div>'; return; }
  if (!rec.report) {
    view.innerHTML = `<div class="card"><p class="hint">这一场只存了汇总数字，没有报告原文，所以看不了详情。</p>
      <p class="hint">用「记录」页把这个报告 id 再取一次就会补上（网站上的报告 15 天内都能取）。</p>
      <p class="hint">报告 id：${esc(rec.rid)}</p></div>`;
    return;
  }
  titleEl.textContent = rec.date || `第 ${rec.seq} 场`;
  backEl.hidden = false;
  let g;
  try {
    g = buildG(rec.rid, rec.report);
  } catch (e) {
    // 报告坏了（三麻、字段缺失、下载不完整）就出一张错误卡，别让页面停在旧视图上
    view.innerHTML = `<div class="card"><p class="err">这一场的报告解析不了：${esc(e.message)}</p>
      <p class="hint">报告 id：${esc(rec.rid)}。重新下载一份再导入通常就好了。</p></div>`;
    return;
  }
  view.innerHTML = `<div class="detail">${detailHtml(g, 10)}</div>
    <div class="card">
      <div class="row">
        <button class="ghost" id="btnMd">导出这份 .md</button>
        <button class="ghost" id="btnDel" style="color:var(--bad)">删除</button>
      </div>
    </div>`;
  const ridEl = view.querySelector('.rid');
  if (ridEl) {
    ridEl.onclick = async () => {
      try { await navigator.clipboard.writeText(ridEl.dataset.rid); toast('报告 id 已复制'); }
      catch { toast(ridEl.dataset.rid); }
    };
  }
  document.getElementById('btnMd').onclick = () => {
    download(`${(rec.date || '').replace(/[: ]/g, '')}_${rec.rid}.md`,
      R.gameMd(g, rec.row['天凤牌谱'] || '', rec.row['备注'] || ''), 'text/markdown');
  };
  document.getElementById('btnDel').onclick = async () => {
    if (!window.confirm(`删除第 ${rec.seq} 场（${rec.date}）？`)) return;
    await db.deleteGame(rec.seq);
    S.games = await db.allMeta();
    toast('已删除');
    location.hash = '#/list';
  };
}

// ---------------------------------------------------------------- 审计
function renderAudit() {
  titleEl.textContent = '审计';
  backEl.hidden = true;
  const opts = [10, 20, 30, 50].map((n) => `<option value="${n}">最近 ${n} 场</option>`).join('');
  view.innerHTML = `
    <div class="card">
      <label class="f"><span>范围</span>
        <select id="auditN">${opts}<option value="0">全部（自己勾选）</option></select>
      </label>
      <button id="btnAudit">开始审计</button>
      <p class="hint">只统计「牌效」类、Q 差 ≥ 0.1、你和 Mortal 都是切牌的手，归成 6 类。</p>
    </div>
    <div id="auditOut"></div>`;
  document.getElementById('btnAudit').onclick = runAudit;
}

async function runAudit() {
  const n = Number(document.getElementById('auditN').value);
  const out = document.getElementById('auditOut');
  const picked = n > 0 ? S.games.slice(-n) : S.games;
  if (!picked.length) { out.innerHTML = '<div class="card"><p class="hint">没有可审计的场次。</p></div>'; return; }
  out.innerHTML = `<div class="card"><p class="hint" id="aprog">正在算…0/${picked.length}</p></div>`;
  const prog = document.getElementById('aprog');
  const games = [];
  const failed = [];
  for (let i = 0; i < picked.length; i += 1) {
    const rec = picked[i];
    if (prog) prog.textContent = `正在算…${i + 1}/${picked.length}`;
    const full = await db.getGame(rec.seq);
    if (!full || !full.report) { failed.push(`#${rec.seq}`); continue; }
    try {
      const [nn, ne, le, hands] = effaudit.classifyReport(full.report);
      for (const h of hands) h.game = `#${rec.seq}`;
      games.push({ label: `#${rec.seq}`, n: nn, ne, le, hands });
    } catch {
      failed.push(`#${rec.seq}`);
    }
    await new Promise((r) => setTimeout(r, 0));   // 让界面刷新
  }
  const res = effaudit.summarize(games);
  out.innerHTML = `<div class="prose">${auditView(res, failed)}</div>`;
}

// ---------------------------------------------------------------- 设置
function renderSettings() {
  titleEl.textContent = '设置';
  backEl.hidden = true;
  const lines = Array.isArray(S.settings.lines) && S.settings.lines.length === 5
    ? S.settings.lines : R.DEFAULT_LINES;
  const mb = (b) => `${(b / 1048576).toFixed(1)} MB`;
  const lineRows = lines.map((l, i) => `
    <div class="line-row">
      <span>${esc(l[0])}</span>
      <input type="number" step="0.1" data-i="${i}" data-f="keep" value="${l[1]}">
      <input type="number" step="0.1" data-i="${i}" data-f="goal" value="${l[2]}">
    </div>`).join('');
  // 每场各记各的口径：从旧备份导入的场次没有 calcVersion，不能算成当前口径
  const stale = S.games.filter((g) => (g.calcVersion || '') !== VERSION).length;
  const recalcHint = S.games.length === 0
    ? '还没有记录，不用重算。'
    : stale === 0
      ? `已有 ${S.games.length} 场都是按 ${VERSION} 口径算的。`
      : `有 ${stale} / ${S.games.length} 场不是 ${VERSION} 口径（旧版本算的，或从旧备份导入）。点上面按钮按新口径重算（会覆盖原有数字，先导出备份）。`;
  view.innerHTML = `
    <div class="card">
      <div class="setting-line"><span>主题</span>
        <select id="theme" style="width:auto">
          <option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option>
        </select>
      </div>
      <div class="setting-line"><span>显示维持线 / 检查点</span>
        <input type="checkbox" id="linesOn" ${S.settings.linesOn ? 'checked' : ''} style="width:20px;height:20px">
      </div>
      <p class="hint">左边是维持线、右边是检查点。开启后详情里多两列，超线标红、达标标绿。</p>
      ${lineRows}
      <button id="btnSaveLines" class="ghost" style="margin-top:8px">保存检查点</button>
    </div>

    <div class="card">
      <div class="setting-line"><span>场次</span><span id="cnt">${S.games.length}</span></div>
      <div class="setting-line"><span>占用</span><span id="usage">…</span></div>
      <div class="row" style="margin-top:10px">
        <button class="ghost" id="btnExportJson">导出备份 JSON</button>
        <button class="ghost" id="btnExportCsv">导出 CSV</button>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="ghost" id="btnImportJson">导入备份 JSON</button>
        <button class="ghost" id="btnDemo">载入示例</button>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="ghost" id="btnLog">导出调试日志</button>
      </div>
      <div class="row" style="margin-top:8px">
        <button class="ghost" id="btnRecalc">按当前口径重算全部</button>
      </div>
      <p class="hint" id="recalcInfo">${recalcHint}</p>
      <p class="hint">备份 JSON 里含每一场的报告原文，换手机时导回去就行；CSV 给 Excel 用。</p>
    </div>

    <div class="card">
      <p class="hint">${VERSION}　计算核心与桌面版逐字段一致。<br>
      报告来自 mjai.ekyu.moe，网站只保留 15 天，所以每场都把原文存进了手机。</p>
      <button class="ghost" id="btnClear" style="color:var(--bad);margin-top:8px">清空全部数据</button>
    </div>`;

  document.getElementById('theme').value = S.settings.theme || 'system';
  document.getElementById('theme').onchange = async (e) => {
    S.settings.theme = e.target.value; await saveSettings();
  };
  document.getElementById('linesOn').onchange = async (e) => {
    S.settings.linesOn = e.target.checked; await saveSettings(); toast('已保存，打开详情看效果');
  };
  document.getElementById('btnSaveLines').onclick = async () => {
    const ls = lines.map((l) => [...l]);
    view.querySelectorAll('input[data-i]').forEach((inp) => {
      const i = Number(inp.dataset.i);
      const v = Number(inp.value);
      if (!Number.isFinite(v) || v < 0) return;
      ls[i][inp.dataset.f === 'keep' ? 1 : 2] = v;
    });
    for (const l of ls) l[2] = Math.min(l[2], l[1]);
    S.settings.lines = ls;
    await saveSettings();
    toast('检查点已保存');
  };
  document.getElementById('btnExportJson').onclick = async () => {
    const games = await db.allGames();
    const packed = await packBackup({
      app: 'mahjong', version: VERSION, exportedAt: new Date().toISOString(),
      settings: S.settings, games,
    });
    const stem = `麻将记录备份_${stamp().replace(/[: ]/g, '')}`;
    logline(`打包完成：${packed.rawKB} KB → ${packed.sizeKB} KB（${packed.compressed ? 'gzip' : '不压缩'}）`);
    if (packed.compressed) await saveFileBinary(`${stem}${packed.ext}`, packed.base64, packed.mime);
    else await saveFile(`${stem}${packed.ext}`, packed.text, packed.mime);
  };
  document.getElementById('btnExportCsv').onclick = async () => {
    const games = await db.allGames();
    await saveFile(`麻将逐场数据_${stamp().replace(/[: ]/g, '')}.csv`, rows.toCsv(games.map((g) => g.row)), 'text/csv');
  };
  document.getElementById('btnImportJson').onclick = () => importBackup();
  document.getElementById('btnDemo').onclick = () => loadDemo();
  document.getElementById('btnLog').onclick = () => exportDebugLog();
  document.getElementById('btnRecalc').onclick = () => recalcAll();
  document.getElementById('btnClear').onclick = async () => {
    if (!window.confirm('清空全部场次？这个不能撤销。建议先导出备份。')) return;
    await db.clearAll();
    S.games = await db.allMeta();
    toast('已清空');
    renderSettings();
  };
  db.estimate().then((est) => {
    const el = document.getElementById('usage');
    if (el) el.textContent = `${mb(est.usage)}${est.quota ? ` / ${mb(est.quota)}` : ''}`;
  });
}

async function importBackup() {
  const f = await pickFileBuffer();
  if (!f) return;
  if (f.error) { toast(f.error); return; }
  let payload;
  try {
    payload = await unpackBackup(f.buffer);
  } catch (e) {
    logline(`导入失败：${e.message}`);
    toast(`这个文件读不了：${e.message}`);
    return;
  }
  const list = Array.isArray(payload) ? payload : payload.games;
  if (!Array.isArray(list)) { toast('这个文件不是备份 JSON'); return; }
  let added = 0;
  for (const g of list) {
    if (!g || typeof g.rid !== 'string' || !/^[0-9a-f]{16}$/.test(g.rid)) continue;
    if (!g.report || !Array.isArray(g.report.mjai_log) || !g.report.review) continue;
    g.rank = Number(g.rank) || 0;
    g.score = Number(g.score) || 0;
    const res = await db.addGame({
      rid: g.rid, key: g.key || rows.timeKey(g.row && g.row['天凤牌谱'], g.date || '', 0),
      date: g.date || '', zhuo: g.zhuo || '', rank: g.rank, rating: g.rating, score: g.score,
      row: g.row || {}, report: g.report, createdAt: g.createdAt || new Date().toISOString(),
      calcVersion: g.calcVersion || '',
    });
    if (!res.existed) added += 1;
  }
  S.games = await db.allMeta();
  toast(`导入完成：新增 ${added} 场，库里共 ${S.games.length} 场`);
  renderSettings();
}

async function loadDemo() {
  try {
    const res = await fetch('./data/report_0b0d6c2336b144eb.json');
    const report = await res.json();
    const g = buildG('0b0d6c2336b144eb', report);
    const row = rows.buildRow(g, '', '示例数据', null);
    const r = await db.addGame({
      rid: '0b0d6c2336b144eb',
      key: rows.timeKey(row['天凤牌谱'], row['日期'], 0),
      date: row['日期'], zhuo: row['卓'], rank: g.rank, rating: g.rating, score: g.score,
      row, report, createdAt: new Date().toISOString(), calcVersion: VERSION,
    });
    S.games = await db.allMeta();
    toast(r.existed ? '示例已经在库里了' : '已载入示例');
    renderSettings();
  } catch (e) { toast(`载入失败：${e.message}`); }
}

// ---------------------------------------------------------------- 路由
const ROUTES = {
  record: renderRecord,
  list: renderList,
  audit: renderAudit,
  settings: renderSettings,
};

async function route() {
  const h = location.hash.replace(/^#\/?/, '') || 'record';
  const [name, arg] = h.split('/');
  document.querySelectorAll('.tabs a').forEach((a) => {
    a.classList.toggle('on', a.dataset.tab === name);
  });
  if (name === 'game' && arg) { await renderGame(arg); return; }
  const fn = ROUTES[name];
  if (fn) await fn();
  else await renderRecord();
}

window.addEventListener('error', (e) => logline(`未捕获错误：${e.message} @ ${e.filename}:${e.lineno}`));
window.addEventListener('unhandledrejection', (e) => logline(`未处理的 Promise 拒绝：${(e.reason && (e.reason.stack || e.reason.message)) || e.reason}`));

async function init() {
  logline(`启动 ${VERSION}（${navigator.userAgent.slice(0, 80)}）`);
  document.getElementById('ver').textContent = VERSION;
  S.settings = (await db.getKV('settings', null)) || S.settings;
  applyTheme();
  applyLines();
  S.games = await db.allMeta();
  S.calcVersion = await db.getKV('calc_version', '');
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (S.settings.theme === 'system') applyTheme();
  });
  backEl.onclick = () => { location.hash = '#/list'; };
  window.addEventListener('hashchange', route);
  // 调试用：?demo=1 直接塞一场示例，方便截图 / 试用
  if (new URLSearchParams(location.search).get('demo') === '1' && !S.games.length) {
    await loadDemo();
  }
  await route();
  // 调试用：?recalc=1 启动后立刻跑一次重算（用来验证这条路径）
  if (new URLSearchParams(location.search).get('recalc') === '1') {
    await recalcAll();
    await route();
  }
}

init();
