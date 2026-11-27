// core.py 的计算部分：把一场的全部数字算成一个对象（golden 文件就是这个结构）
import * as mr from './mr.js';
import * as effaudit from './effaudit.js';

/** 一场的全部数据。opts.lobby 是卓（一般/上级/…），opts.link 是天凤牌谱链接 */
export function compute(reportId, report, opts = {}) {
  const target = report.player_id;
  const rows = mr.analyze(report);
  const s = mr.summary(rows);
  const [score, rank] = mr.finalScores(report);
  const ls = mr.logStats(report);
  const pr = mr.pressure(rows, target);

  const eff = s['牌效_n'] ? (s['牌效_raw'] / s['牌效_n']) * 100 : null;
  const dfn = s['防守_n'] ? (s['防守_raw'] / s['防守_n']) * 100 : null;
  const five = [
    { name: '合计失分', value: s.loss, note: '' },
    { name: '每100次牌效决策', value: eff, note: `${s['牌效_n']} 次` },
    { name: '每100次防守决策', value: dfn, note: `${s['防守_n']} 次` },
    { name: '压力分数', value: pr.merged.per100, note: `${pr.merged.n} 次` },
    { name: '严重失误', value: s.severe, note: `${Math.round((s.severe * s.n) / 100)} 次` },
  ];

  const rowsByCat = {};
  for (const cat of mr.CATS) {
    // 按样本数判断，不能按失分判断：一类决策全对（失分 0）时也要留在表里
    if (s[`${cat}_n`] > 0) rowsByCat[cat] = s[`${cat}_n`];
  }

  const top10 = [...rows]
    .sort((a, b) => b.diff - a.diff)
    .slice(0, 10)
    .map((r) => ({
      kyoku: mr.kyokuName(r.snap),
      junme: r.junme,
      cat: r.cat,
      diff: r.diff,
      tehai: r.entry.state.tehai,
      // golden 用的是「这 14 张现在几向听」，不是报告里的 pre-draw shanten
      shanten: mr.shanten(r.entry.state.tehai, (r.entry.state.fuuros || []).length),
      actual: r.actual,
      expected: r.expected,
      q_actual: r.q_actual,
      q_expected: r.q_expected,
    }));

  const [nAll, nEff, lossEff, hands] = effaudit.classifyReport(report);
  for (const h of hands) h.game = reportId;
  const auditRaw = effaudit.summarize([{
    label: reportId, n: nAll, ne: nEff, le: lossEff, hands,
  }]);

  const full = {
    rid: reportId,
    d: report,
    rows,
    target,
    s,
    score,
    rank,
    ls,
    pr,
    rating: report.review.rating * 100,
    report_id: reportId,
    lobby: opts.lobby || mr.reportMeta(report).lobby || '',
    n_decisions: s.n,
    five,
    summary: s,
    log_stats: ls,
    pressure: pr,
    rows_by_cat: rowsByCat,
    top10,
    audit: {
      games: auditRaw.games,
      n: auditRaw.n,
      ne: auditRaw.ne,
      le: auditRaw.le,
      cats: auditRaw.cats,
      bysh: Object.fromEntries([...auditRaw.bysh.entries()]
        .map(([k, v]) => [String(k), Object.fromEntries(v)])),
    },
    audit_hands_count: hands.length,
  };
  return full;
}

/** 只保留 golden 文件里的 15 个字段（顺序也照 golden） */
export function toGolden(g) {
  return {
    report_id: g.report_id,
    rank: g.rank,
    score: g.score,
    rating: g.rating,
    target: g.target,
    lobby: g.lobby,
    n_decisions: g.n_decisions,
    five: g.five,
    summary: g.summary,
    log_stats: g.log_stats,
    pressure: g.pressure,
    rows_by_cat: g.rows_by_cat,
    top10: g.top10,
    audit: g.audit,
    audit_hands_count: g.audit_hands_count,
  };
}

/** 便利函数：只看 5 项 */
export function fiveOf(report) {
  return compute(report.report_id || '', report).five;
}
