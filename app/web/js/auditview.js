// 审计视图：内容和桌面版 audit_html 一致（同样的数字、同样的文字），只把两张宽表换成手机能看的卡片：
//   ① 5 列的类别表 → 每个类别一张卡（手数 / 失分 / 占牌效 / Q差≥1）
//   ② 8 列的「按向听」表 → 每个向听一张卡
import * as R from '../src/render.js';
import * as effaudit from '../src/effaudit.js';

const esc = (s) => String(s === null || s === undefined ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export function auditView(res, failed = []) {
  const out = [];
  out.push(`<div class="h1">牌效审计　${res.games} 场　${res.n} 手决策</div>`);
  out.push(`<p class="dim">牌效决策 ${res.ne} 次，牌效失分 ${R.fixed(res.le, 1)}（每 100 手 ${R.fixed((res.le / Math.max(1, res.n)) * 100, 2)}）</p>`);
  if (failed.length) out.push(`<p class="bad">没取到报告、已跳过：${esc(failed.join('、'))}</p>`);

  // ① 类别
  out.push('<div class="h2">按类别</div><div class="shcards">');
  for (const c of [...res.cats].sort((a, b) => b.loss - a.loss)) {
    const cls = c.big >= 3 ? ' class="bad"' : '';
    out.push(`<div class="shcard"><h4${cls}>${esc(c.k)}　<span class="dim">${c.n} 手</span></h4>`
      + `<div class="line"><span class="n">失分</span><span>${R.fixed(c.loss, 1)}</span></div>`
      + `<div class="line"><span class="n">占牌效</span><span>${R.fixed(c.share_eff, 1)}%</span></div>`
      + `<div class="line"><span class="n">Q差 ≥ 1</span><span>${c.big}</span></div></div>`);
  }
  out.push('</div>');

  // ② 按向听
  const cats = effaudit.CATS;
  const keys = [...res.bysh.keys()].sort((a, b) => a - b);
  out.push('<div class="h2">按打牌前的向听（各类失分）</div><div class="shcards">');
  for (const sh of keys) {
    const cnt = res.bysh.get(sh);
    const lab = sh === 0 ? '听牌' : (sh < 4 ? `${sh} 向听` : '4 向听+');
    const total = cats.reduce((s, k) => s + (cnt.get(k) || 0), 0);
    const lines = cats.filter((k) => cnt.get(k))
      .map((k) => `<div class="line"><span class="n">${esc(k)}</span><span>${R.fixed(cnt.get(k), 1)}</span></div>`).join('');
    out.push(`<div class="shcard"><h4>${lab}　<span class="dim">合计 ${R.fixed(total, 1)}</span></h4>${lines}</div>`);
  }
  out.push('</div>');

  // ③ 各类最大的几手（和桌面版一字不差）
  out.push('<div class="h2">各类最大的几手</div>');
  for (const k of cats) {
    const hs = res.hands.filter((h) => h.k === k).sort((a, b) => b.diff - a.diff).slice(0, 4);
    if (!hs.length) continue;
    out.push(`<div class="h3">【${esc(k)}】</div>`);
    for (const h of hs) {
      out.push(`<p><span class="${h.diff >= 1 ? 'bad' : 'h3'}">${esc(h.game || '')} `
        + `${esc(h.kyoku)} · ${h.junme} 巡　差 ${R.fixed(h.diff, 2)}</span><br>`
        + `<span class="dim">手牌　</span>${R.handStr(h.hand)}<br>`
        + `<span class="dim">你　　</span>${R.actStr(h.a)}（${h.sa} 向听，进张 ${h.ua}）<br>`
        + `<span class="dim">Mortal　</span><span class="mortal">${R.actStr(h.x)}`
        + `（${h.sx} 向听，进张 ${h.ux}）</span></p>`);
    }
  }
  return out.join('\n');
}
