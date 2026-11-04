// Rotación del aporte mensual. Es la misma regla que scripts/radar/plan.py (las pruebas verifican que coincidan).

export function instrumentsFor(amount) {
  if (amount < 200) return 1;
  if (amount < 1000) return 2;
  return 3;
}

export function sleeveValues(sleeves, values) {
  const owner = new Map();
  sleeves.forEach((s, i) => s.candidatos.forEach((t) => { if (!owner.has(t)) owner.set(t, i); }));
  const per = sleeves.map(() => 0);
  let others = 0;
  for (const [t, v] of Object.entries(values)) {
    if (owner.has(t)) per[owner.get(t)] += v; else others += v;
  }
  return { per, others };
}

export function pickTicker(sleeve, ranking, signals, held) {
  const cands = sleeve.candidatos;
  if (!cands.length) return null;
  if (cands.length === 1) return cands[0];
  const usable = cands.filter((t) => signals[t] !== "VENTA");
  if (!usable.length) return null;
  usable.sort((a, b) => ((ranking[b] || 0) - (ranking[a] || 0)) || (cands.indexOf(a) - cands.indexOf(b)));
  const best = usable[0];
  const bestScore = ranking[best] || 0;
  for (const t of usable) {
    if ((held[t] || 0) > 0 && (ranking[t] || 0) >= bestScore - 3) return t;
  }
  return best;
}

export function suggest(sleeves, values, amount, ranking, signals, maxInstruments = null) {
  if (!(amount > 0) || !sleeves.length) return [];
  const { per, others } = sleeveValues(sleeves, values);
  const total = per.reduce((a, b) => a + b, 0) + others;
  const after = total + amount;
  const k = maxInstruments || instrumentsFor(amount);
  const gapOf = (i) => (sleeves[i].peso / 100) * after - per[i];
  const order = sleeves.map((_, i) => i).sort((a, b) => (gapOf(b) - gapOf(a)) || (a - b));

  let picks = [];
  for (const i of order) {
    if (picks.length >= k) break;
    const gap = gapOf(i);
    if (gap <= 0 && picks.length) break;
    const t = pickTicker(sleeves[i], ranking, signals, values);
    if (t === null) continue;
    picks.push({ i, ticker: t, gap: Math.max(gap, 0) });
  }
  if (!picks.length) return [];

  const totalGap = picks.reduce((s, p) => s + p.gap, 0);
  const raw = totalGap > 0 ? picks.map((p) => (amount * p.gap) / totalGap) : picks.map(() => amount / picks.length);
  const minTicket = Math.max(20, amount * 0.1);
  let keep = raw.map((a, j) => (a >= minTicket ? j : -1)).filter((j) => j >= 0);
  if (!keep.length) keep = [0];
  if (!keep.includes(0)) keep = [0, ...keep];
  const rawKept = keep.map((j) => raw[j]);
  rawKept[0] += amount - rawKept.reduce((a, b) => a + b, 0);
  picks = keep.map((j) => picks[j]);

  const amounts = rawKept.map((a) => Math.floor(a + 1e-9));
  amounts[0] += Math.round(amount) - amounts.reduce((a, b) => a + b, 0);

  return picks.map((p, j) => {
    const s = sleeves[p.i];
    const currentPct = total > 0 ? (per[p.i] / total) * 100 : 0;
    return {
      ticker: p.ticker,
      monto_usd: amounts[j],
      grupo_id: s.id,
      grupo: s.grupo,
      nombre_grupo: s.nombre,
      actual_pct: Math.round(currentPct * 10) / 10,
      objetivo_pct: Math.round(s.peso * 10) / 10,
      puntaje: ranking[p.ticker] ?? null,
      senal: signals[p.ticker] ?? null,
      falta_usd: Math.round(p.gap * 100) / 100,
    };
  });
}
