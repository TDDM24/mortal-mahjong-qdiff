// 详情页（手机专用排版）：重点 5 项一张表，辅助 / 战绩 / 压力三个折叠，Q 差最大的 10 手收进二级折叠 + 卡片。
// 数字和文案仍来自同一套计算；gameHtml() 保持不动（导出 .md、和桌面版对照都用它）。
import * as R from '../src/render.js';
import * as mr from '../src/mr.js';
import { tileIndex } from '../src/tiles.js';

const esc = (s) => String(s === null || s === undefined ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

function fiveTable(g) {
  const on = R.state.LINES_ON;
  const head = `<tr><th>项目</th><th class="r">本场</th>${on ? '<th class="r">维持</th><th class="r">检查</th>' : ''}</tr>`;
  const rows = R.state.LINES.map(([name, keep, goal, keepS, goalS], i) => {
    const f = g.five[i] || {};
    const st = R.lineState(name, f.value);
    const cls = st ? `r v ${st}` : 'r v';
    const note = f.note ? `<small>（${esc(f.note)}）</small>` : '';
    const extra = on ? `<td class="r dim">≤${keepS}</td><td class="r dim">≤${goalS}</td>` : '';
    return `<tr><td class="k">${esc(name)}</td><td class="${cls}">${R.fmt5(name, f.value)}${note}</td>${extra}</tr>`;
  }).join('');
  return `<table class="five-m"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
}

const kv = (rows) => rows.map(([k, v]) => `<div class="kvrow"><span class="k">${esc(k)}</span><b>${v}</b></div>`).join('');

function handCard(r, target) {
  let ea = '';
  let ee = '';
  if (r.cat === '防守' && r.snap) {
    ea = `，${mr.worstSafety(r.snap, target, tileIndex(r.actual.pai))[1] || ''}`;
    if (r.expected.type === 'dahai') ee = `，${mr.worstSafety(r.snap, target, tileIndex(r.expected.pai))[1] || ''}`;
  }
  const sh = mr.shanten(r.entry.state.tehai, (r.entry.state.fuuros || []).length);
  const diffCls = r.diff >= 1 ? 'bad' : 'h3';
  return `<div class="handcard">
    <div class="hc-top"><span class="hc-kyoku">${esc(mr.kyokuName(r.snap))} · ${r.junme} 巡</span>
      <span class="pill">${esc(r.cat)}</span><span class="hc-diff ${diffCls}">差 ${R.fixed(r.diff, 2)}</span></div>
    <div class="hc-hand">${R.handStr(r.entry.state.tehai)}<span class="dim">（${sh} 向听）</span></div>
    <div class="hc-line"><span class="dim">你</span>${R.actStr(r.actual)}<span class="dim">（Q ${R.fixed(r.q_actual, 2)}${esc(ea)}）</span></div>
    <div class="hc-line mortal"><span class="dim">Mortal</span>${R.actStr(r.expected)}<span class="dim">（Q ${R.fixed(r.q_expected, 2)}${esc(ee)}）</span></div>
  </div>`;
}

/** g 来自 compute()；top 默认 10 */
export function detailHtml(g, top = 10, opts = {}) {
  const s = g.s;
  const pr = g.pr;
  const ls = g.ls;
  const open = opts.open ? ' open' : '';
  const hands = [...g.rows].sort((a, b) => b.diff - a.diff).slice(0, top);

  return `
<div class="lead"><b class="rating">${R.fixed(g.rating, 1)}</b><span class="rating-label">Rating</span><span class="dim">${s.n} 手</span></div>
<div class="h1">第 ${Number(g.rank)} 位　${Number(g.score)} 点${g.lobby ? `　${esc(g.lobby)}卓` : ''}</div>
<div class="rid" data-rid="${esc(g.rid)}">报告 ${esc(g.rid)}</div>

${fiveTable(g)}

<details class="fold"${open}><summary>辅助</summary><div class="fold-body">
  ${kv([
    ['牌效', R.fixed(s['牌效'], 2)],
    ['防守', R.fixed(s['防守'], 2)],
    ['副露压力下', R.fixed(s['副露压力下'], 2)],
    ['立直判断', R.fixed(s['立直判断'], 2)],
    ['鸣牌判断', R.fixed(s['鸣牌判断'], 2)],
  ])}
</div></details>

<details class="fold"${open}><summary>战绩</summary><div class="fold-body">
  ${kv([
    ['和了', `${R.fixed(ls.win_rate, 1)}%`],
    ['放铳', `${R.fixed(ls.deal_rate, 1)}%`],
    ['立直', `${R.fixed(ls.riichi_rate, 1)}%`],
    ['副露', `${R.fixed(ls.meld_rate, 1)}%`],
  ])}
</div></details>

<details class="fold"${open}><summary>压力</summary><div class="fold-body">
  ${kv([
    ['立直威胁', `${R.fixed(pr.riichi.per100, 1)}<span class="dim">（${pr.riichi.n} 次）</span>`],
    ['隐形威胁', `${R.fixed(pr.hidden.per100, 1)}<span class="dim">（${pr.hidden.n} 次）</span>`],
    ['无威胁', `${R.fixed(pr.none.per100, 1)}<span class="dim">（${pr.none.n} 次）</span>`],
  ])}
</div></details>

<details class="fold"${open}><summary>Q 差最大的 ${top} 手</summary><div class="fold-body hands">
  ${hands.map((r) => handCard(r, g.target)).join('')}
</div></details>`;
}
