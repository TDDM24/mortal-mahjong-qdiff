// core.py 的渲染部分：把一场的数据拼成 HTML / Markdown。字符串要和 Python 版逐字节一致。
import * as mr from './mr.js';
import * as effauditMod from './effaudit.js';
import { pyRound } from './pyround.js';
import { tileIndex } from './tiles.js';

export const HON = {
  E: '东', S: '南', W: '西', N: '北', P: '白', F: '發', C: '中',
};
// 后两位是 Python 里 str(keep) / str(goal) 的结果：Python 的 1.0 会打成 "1.0"，JS 的 1.0 是 "1"，
// 所以把显示用的字符串一起存下来（DEFAULT_LINES 里 10 是 int、1.0 是 float，str 结果不同）
export const DEFAULT_LINES = [
  ['合计失分', 10, 7, '10', '7'],
  ['每100次牌效决策', 13, 8, '13', '8'],
  ['每100次防守决策', 14, 10, '14', '10'],
  ['压力分数', 16, 11, '16', '11'],
  ['严重失误', 2.3, 1.0, '2.3', '1.0'],
];
export const state = {
  MODE: 'self',
  LINES: DEFAULT_LINES.map((x) => [...x]),
  LINES_ON: false,
};

export function setLines(lines, on = null) {
  if (on !== null) state.LINES_ON = !!on;
  const out = [];
  const pyf = (x) => (Number.isInteger(Number(x)) ? `${Number(x)}.0` : String(Number(x)));
  for (const item of lines) {
    try {
      out.push([String(item[0]), Number(item[1]), Number(item[2]), pyf(item[1]), pyf(item[2])]);
    } catch { /* 跳过坏行 */ }
  }
  if (out.length === DEFAULT_LINES.length) state.LINES = out;
}

/** Python 的 f'{v:.2f}' 也是五成双（基于精确值），所以走 pyRound；
 *  另外 Python 会把 -0.0004 打成 "-0.00"，而 JS 的 (-0).toFixed() 会丢掉负号，这里补回来。 */
export function fixed(v, nd) {
  const r = pyRound(v, nd);
  const neg = r < 0 || Object.is(r, -0);
  return (neg ? '-' : '') + Math.abs(r).toFixed(nd);
}

/** 超维持线 → 'bad'；达检查点 → 'good' */
export function lineState(name, value) {
  if (!state.LINES_ON || value === null) return '';
  for (const [n, keep, goal] of state.LINES) {
    if (n === name) {
      if (value > keep) return 'bad';
      if (value <= goal) return 'good';
    }
  }
  return '';
}

export function getRid(text) {
  const m = /([0-9a-f]{16})/.exec((text || '').trim());
  return m ? m[1] : null;
}

export function tname(t) {
  if (t in HON) return HON[t];
  return t.endsWith('r') ? `0${t[1]}` : t;
}

/** 手牌排好：万筒索各自连写，字牌放最后；红五显示 0 */
/** 拼 HTML 前统一转义：报告/备份文件都是外部输入 */
export function esc(v) {
  return String(v === null || v === undefined ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function handStr(tiles) {
  const g = { m: [], p: [], s: [] };
  const hon = [];
  for (const t of [...tiles].sort((a, b) => tileIndex(a) - tileIndex(b))) {
    if (!t || t === '?') { hon.push('?'); continue; }
    if (t in HON) hon.push(HON[t]);
    else g[t[1]].push(t.endsWith('r') ? '0' : t[0]);
  }
  const parts = [];
  for (const [k, v] of Object.entries(g)) if (v.length) parts.push(v.join('') + k);
  if (hon.length) parts.push(hon.join(''));
  return esc(parts.join(' '));
}

export function actStr(a) {
  // 牌名来自报告 JSON，属外部输入；这个函数只产纯文本，统一转义
  if (a.type === 'dahai') return esc(`${a.tsumogiri ? '摸切 ' : ''}${tname(a.pai || '')}`);
  return esc(mr.actCn(a));
}

export function fmt5(name, v) {
  if (v === null || v === undefined) return '—';
  return ['合计失分', '严重失误'].includes(name) ? fixed(v, 2) : fixed(v, 1);
}

export function verdict(five) {
  if (state.MODE !== 'self' || !state.LINES_ON) return '';
  let over = 0;
  let good = 0;
  state.LINES.forEach(([n, keep, goal], i) => {
    const v = five[i] ? (five[i].value !== undefined ? five[i].value : five[i][0]) : null;
    if (v !== null && v !== undefined && v > keep) over += 1;
    if (v !== null && v !== undefined && v <= goal) good += 1;
  });
  const parts = [];
  if (over) parts.push(`超维持线 ${over} 项`);
  if (good) parts.push(`达检查点 ${good} 项`);
  return parts.join('，') || '都在线内';
}

export function verdictShort(five) {
  if (state.MODE !== 'self' || !state.LINES_ON) return '';
  let over = 0;
  let good = 0;
  state.LINES.forEach(([n, keep, goal], i) => {
    const v = five[i] ? (five[i].value !== undefined ? five[i].value : five[i][0]) : null;
    if (v !== null && v !== undefined && v > keep) over += 1;
    if (v !== null && v !== undefined && v <= goal) good += 1;
  });
  if (over && good) return `超${over} 达${good}`;
  if (over) return `超${over}`;
  if (good) return `达${good}`;
  return '在线内';
}

/** 一手错牌的 HTML 片段（详情窗口和 md 共用） */
export function rowHtml(r, target) {
  const st = r.entry.state;
  const sh = mr.shanten(st.tehai, (st.fuuros || []).length);
  const diffCls = r.diff >= 1.0 ? 'bad' : 'h3';
  let ea = '';
  let ee = '';
  if (r.cat === '防守' && r.snap) {
    ea = `，${mr.worstSafety(r.snap, target, tileIndex(r.actual.pai))[1] || ''}`;
    if (r.expected.type === 'dahai') {
      ee = `，${mr.worstSafety(r.snap, target, tileIndex(r.expected.pai))[1] || ''}`;
    }
  }
  return `<p><span class="h3">${mr.kyokuName(r.snap)} · ${r.junme} 巡　[${r.cat}]　</span>`
    + `<span class="${diffCls}">差 ${fixed(r.diff, 2)}</span><br>`
    + `<span class="dim">手牌　</span>${esc(handStr(st.tehai))}<span class="dim">（${sh} 向听）</span><br>`
    + `<span class="dim">你　　</span>${esc(actStr(r.actual))}（Q ${fixed(r.q_actual, 2)}${esc(ea)}）<br>`
    + `<span class="dim">Mortal　</span><span class="mortal">${esc(actStr(r.expected))}`
    + `（Q ${fixed(r.q_expected, 2)}${ee}）</span></p>`;
}

export function gameHtml(g, top = 10) {
  const { s, pr, ls } = g;
  const rows = [];
  const row = (name, keep, goal, v, n, keepS, goalS) => {
    const st = lineState(name, v);
    const cls = st ? `v ${st}` : 'v';
    const note = n && v !== null && v !== undefined ? `（${n}）` : '';
    const tail = state.LINES_ON ? `<td class="dim">≤${keepS}</td><td class="dim">≤${goalS}</td>` : '';
    return `<tr><td class="k">${name}</td><td class="${cls}">${fmt5(name, v)}`
      + `<span class="dim">${note}</span></td>${tail}</tr>`;
  };
  state.LINES.forEach(([name, keep, goal, keepS, goalS], i) => {
    const f = g.five[i] || {};
    rows.push(row(name, keep, goal, f.value, f.note, keepS, goalS));
  });
  const fiveRows = rows.join('');
  const topRows = [...g.rows].sort((a, b) => b.diff - a.diff).slice(0, top);
  const slRows = topRows.map((r) => rowHtml(r, g.target)).join('');
  return `
<div class="h1">第 ${esc(g.rank)} 位　${esc(g.score)} 点${g.lobby ? `　${esc(g.lobby)}卓` : ''}　rating ${fixed(g.rating, 1)}　${s.n} 手</div>
<div class="dim">报告 ${esc(g.rid)}</div>
<div class="h2">重点 5 项</div>
<table class="five">
<tr><th>项目</th><th>本场</th>${state.LINES_ON ? '<th>维持线</th><th>检查点</th>' : ''}</tr>${fiveRows}
</table>
<p><span class="h2">辅助　</span>牌效 ${fixed(s['牌效'], 2)} · 防守 ${fixed(s['防守'], 2)} · 副露压力下 ${fixed(s['副露压力下'], 2)}
 · 立直 ${fixed(s['立直判断'], 2)} · 鸣牌 ${fixed(s['鸣牌判断'], 2)}</p>
<p><span class="h2">战绩　</span>和了 ${fixed(ls.win_rate, 1)}% · 放铳 ${fixed(ls.deal_rate, 1)}%
 · 立直 ${fixed(ls.riichi_rate, 1)}% · 副露 ${fixed(ls.meld_rate, 1)}%</p>
<p><span class="h2">压力　</span>立直威胁 ${fixed(pr.riichi.per100, 1)}（${pr.riichi.n} 次）
 · 隐形威胁 ${fixed(pr.hidden.per100, 1)}（${pr.hidden.n} 次）
 · 无威胁 ${fixed(pr.none.per100, 1)}（${pr.none.n} 次）</p>
<div class="h2">Q 差最大的 ${top} 手</div>${slRows}
`;
}

export function gameMd(g, link = '', note = '') {
  const L = [
    `# 第 ${g.rank} 位 ${g.score} 点 · rating ${fixed(g.rating, 1)}`, '',
    `- 报告：<https://mjai.ekyu.moe/killerducky/?data=/report/${g.rid}.json>`,
    `- 原始数据：\`${g.rid}.json\``,
  ];
  if (link) L.push(`- 牌谱：<${link}>`);
  if (note) L.push(`- 备注：${note}`);
  L.push('', '## 重点 5 项', '', '| 项目 | 本场 | 维持线 | 检查点 |', '|---|---|---|---|');
  state.LINES.forEach(([name, keep, goal, keepS, goalS], i) => {
    const f = g.five[i] || {};
    const v = f.value;
    const noteTxt = f.note && v !== null && v !== undefined ? `（${f.note}）` : '';
    L.push(`| ${name} | ${fmt5(name, v)}${noteTxt} | ≤${keepS} | ≤${goalS} |`);
  });
  const { s, ls, pr } = g;
  L.push('', `- 辅助：牌效 ${fixed(s['牌效'], 2)}、防守 ${fixed(s['防守'], 2)}、副露压力下 ${fixed(s['副露压力下'], 2)}、`
    + `立直 ${fixed(s['立直判断'], 2)}、鸣牌 ${fixed(s['鸣牌判断'], 2)}`,
  `- 战绩：和了 ${fixed(ls.win_rate, 1)}%、放铳 ${fixed(ls.deal_rate, 1)}%、`
    + `立直 ${fixed(ls.riichi_rate, 1)}%、副露 ${fixed(ls.meld_rate, 1)}%`,
  `- 压力：立直威胁 ${fixed(pr.riichi.per100, 1)}（${pr.riichi.n} 次）、`
    + `隐形威胁 ${fixed(pr.hidden.per100, 1)}（${pr.hidden.n} 次）`,
  '', '## Q 差最大的 10 手', '', '| # | 局 · 巡 | 类别 | 手牌 | 你 | Mortal | 差 |', '|---|---|---|---|---|---|---|');
  [...g.rows].sort((a, b) => b.diff - a.diff).slice(0, 10).forEach((r, i) => {
    L.push(`| ${i + 1} | ${mr.kyokuName(r.snap)} · ${r.junme} | ${r.cat} | `
      + `${handStr(r.entry.state.tehai)} | ${actStr(r.actual)}（${fixed(r.q_actual, 2)}） | `
      + `${actStr(r.expected)}（${fixed(r.q_expected, 2)}） | ${fixed(r.diff, 2)} |`);
  });
  return `${L.join('\n')}\n`;
}

export function auditHtml(res, failed = []) {
  const out = [`<div class="h1">牌效审计　${res.games} 场　${res.n} 手决策</div>`];
  out.push(`<p class="dim">牌效决策 ${res.ne} 次，牌效失分 ${fixed(res.le, 1)}`
    + `（每 100 手 ${fixed((res.le / Math.max(1, res.n)) * 100, 2)}）</p>`);
  if (failed.length) out.push(`<p class="bad">没取到报告、已跳过：${failed.join('、')}</p>`);
  out.push('<table class="grid"><tr><th>类别</th><th>手数</th><th>失分</th><th>占牌效</th><th>Q差≥1</th></tr>');
  for (const c of [...res.cats].sort((a, b) => b.loss - a.loss)) {
    const cls = c.big >= 3 ? ' class="bad"' : '';
    out.push(`<tr${cls}><td>${c.k}</td><td>${c.n}</td><td>${fixed(c.loss, 1)}</td>`
      + `<td>${fixed(c.share_eff, 1)}%</td><td>${c.big}</td></tr>`);
  }
  out.push('</table>');
  out.push('<div class="h2">按打牌前的向听（各类失分）</div>');
  const names = { 'Mortal 宁可少进张': 'M宁可少进张' };
  out.push('<table class="grid"><tr><th>向听</th>'
    + effauditMod.CATS.map((k) => `<th>${names[k] || k}</th>`).join('') + '<th>合计</th></tr>');
  const keys = [...res.bysh.keys()].sort((a, b) => a - b);
  for (const sh of keys) {
    const cnt = res.bysh.get(sh);
    const lab = sh === 0 ? '听牌' : (sh < 4 ? `${sh} 向听` : '4 向听+');
    const vals = effauditMod.CATS.map((k) => cnt.get(k) || 0);
    out.push(`<tr><td>${lab}</td>`
      + vals.map((v) => (v ? `<td>${fixed(v, 1)}</td>` : '<td class="dim">·</td>')).join('')
      + `<td>${fixed(vals.reduce((a, b) => a + b, 0), 1)}</td></tr>`);
  }
  out.push('</table>');
  out.push('<div class="h2">各类最大的几手</div>');
  for (const k of effauditMod.CATS) {
    const hs = res.hands.filter((h) => h.k === k).sort((a, b) => b.diff - a.diff).slice(0, 4);
    if (!hs.length) continue;
    out.push(`<div class="h3">【${k}】</div>`);
    for (const h of hs) {
      out.push(`<p><span class="${h.diff >= 1 ? 'bad' : 'h3'}">${h.game || ''} `
        + `${h.kyoku} · ${h.junme} 巡　差 ${fixed(h.diff, 2)}</span><br>`
        + `<span class="dim">手牌　</span>${handStr(h.hand)}<br>`
        + `<span class="dim">你　　</span>${actStr(h.a)}（${h.sa} 向听，进张 ${h.ua}）<br>`
        + `<span class="dim">Mortal　</span><span class="mortal">${actStr(h.x)}`
        + `（${h.sx} 向听，进张 ${h.ux}）</span></p>`);
    }
  }
  return out.join('\n');
}
