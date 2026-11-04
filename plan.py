"""Plan de inversión sin IA: cartera real, distribución objetivo, puntajes y rotación del aporte mensual.

La misma regla de rotación está escrita en docs/rotation.js para que la web
calcule al instante con cualquier monto. Las pruebas verifican que coincidan.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

# ---------- cartera real ----------


def holdings_from_movements(movements: List[dict]) -> Dict[str, dict]:
    """Suma compras y ventas. Cada movimiento: {fecha, ticker, tipo: compra|venta, monto_usd, precio_usd}."""
    out: Dict[str, dict] = {}
    for m in sorted(movements, key=lambda x: str(x.get("fecha", ""))):
        t = str(m.get("ticker", "")).strip().upper()
        price = float(m.get("precio_usd") or 0)
        amount = float(m.get("monto_usd") or 0)
        if not t or price <= 0 or amount <= 0:
            continue
        qty = float(m["cantidad"]) if m.get("cantidad") else amount / price
        h = out.setdefault(t, {"ticker": t, "cantidad": 0.0, "invertido_usd": 0.0})
        if str(m.get("tipo", "compra")).lower() == "venta":
            if h["cantidad"] > 0:
                frac = min(qty / h["cantidad"], 1.0)
                h["invertido_usd"] *= (1 - frac)
                h["cantidad"] = max(h["cantidad"] - qty, 0.0)
        else:
            h["cantidad"] += qty
            h["invertido_usd"] += amount
    return {t: h for t, h in out.items() if h["cantidad"] > 1e-9}


def value_holdings(holdings: Dict[str, dict], prices: Dict[str, float]) -> List[dict]:
    rows = []
    for t, h in holdings.items():
        p = prices.get(t)
        value = h["cantidad"] * p if p else None
        rows.append({
            **h,
            "precio_usd": p,
            "valor_usd": None if value is None else round(value, 2),
            "resultado_usd": None if value is None else round(value - h["invertido_usd"], 2),
            "resultado_pct": None if value is None or not h["invertido_usd"]
            else round((value / h["invertido_usd"] - 1) * 100, 2),
        })
    rows.sort(key=lambda r: -(r["valor_usd"] or 0))
    return rows


# ---------- distribución objetivo ----------


def normalize_sleeves(config_sleeves: List[dict]) -> List[dict]:
    """Normaliza los grupos de config.json: pesos que suman 100 y candidatos como lista de tickers."""
    total = sum(float(s.get("peso", 0)) for s in config_sleeves) or 1.0
    out, seen = [], set()
    for i, s in enumerate(config_sleeves):
        cands = []
        names, holders = {}, {}
        for c in s.get("candidatos", []):
            t = (c.get("ticker") if isinstance(c, dict) else c) or ""
            t = str(t).strip().upper()
            if t and t not in seen:
                seen.add(t)
                cands.append(t)
                if isinstance(c, dict) and c.get("nombre"):
                    names[t] = c["nombre"]
                if isinstance(c, dict) and c.get("titular_patentes"):
                    holders[t] = c["titular_patentes"]
        out.append({
            "id": f"g{i}",
            "grupo": s.get("grupo", "Núcleo"),
            "nombre": s.get("nombre", f"Grupo {i + 1}"),
            "peso": round(float(s.get("peso", 0)) * 100 / total, 4),
            "candidatos": cands,
            "nombres": names,
            "titulares_patentes": holders,
            "patentes": bool(s.get("patentes")),
        })
    return out


def sleeve_values(sleeves: List[dict], values: Dict[str, float]) -> tuple[list, float]:
    owner = {}
    for i, s in enumerate(sleeves):
        for t in s["candidatos"]:
            owner.setdefault(t, i)
    per = [0.0] * len(sleeves)
    others = 0.0
    for t, v in values.items():
        if t in owner:
            per[owner[t]] += v
        else:
            others += v
    return per, others


# ---------- rotación del aporte ----------


def instruments_for(amount: float) -> int:
    """Con montos chicos conviene concentrar el aporte para no pagar varias comisiones mínimas."""
    if amount < 200:
        return 1
    if amount < 1000:
        return 2
    return 3


def pick_ticker(sleeve: dict, ranking: Dict[str, float], signals: Dict[str, str], held: Dict[str, float]) -> Optional[str]:
    cands = sleeve["candidatos"]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    usable = [t for t in cands if signals.get(t) != "VENTA"]
    if not usable:
        return None
    usable.sort(key=lambda t: (-(ranking.get(t) or 0), cands.index(t)))
    best = usable[0]
    best_score = ranking.get(best) or 0
    for t in usable:
        if held.get(t, 0) > 0 and (ranking.get(t) or 0) >= best_score - 3:
            return t
    return best


def suggest(sleeves: List[dict], values: Dict[str, float], amount: float,
            ranking: Dict[str, float], signals: Dict[str, str],
            max_instruments: Optional[int] = None) -> List[dict]:
    """Reparte el aporte entre los grupos más atrasados respecto de su peso objetivo."""
    if amount <= 0 or not sleeves:
        return []
    per, others = sleeve_values(sleeves, values)
    total = sum(per) + others
    after = total + amount
    k = max_instruments or instruments_for(amount)
    order = sorted(range(len(sleeves)), key=lambda i: (-(sleeves[i]["peso"] / 100 * after - per[i]), i))

    picks = []
    for i in order:
        if len(picks) >= k:
            break
        gap = sleeves[i]["peso"] / 100 * after - per[i]
        if gap <= 0 and picks:
            break
        t = pick_ticker(sleeves[i], ranking, signals, values)
        if t is None:
            continue
        picks.append({"i": i, "ticker": t, "gap": max(gap, 0.0)})
    if not picks:
        return []

    gaps = [p["gap"] for p in picks]
    total_gap = sum(gaps)
    raw = [amount * g / total_gap for g in gaps] if total_gap > 0 else [amount / len(picks)] * len(picks)

    # Sin montos muy chicos: lo que quede debajo del mínimo pasa al primero.
    min_ticket = max(20.0, amount * 0.1)
    keep = [j for j, a in enumerate(raw) if a >= min_ticket] or [0]
    if 0 not in keep:
        keep = [0] + keep
    raw_kept = [raw[j] for j in keep]
    raw_kept[0] += amount - sum(raw_kept)
    picks = [picks[j] for j in keep]

    amounts = [math.floor(a + 1e-9) for a in raw_kept]
    amounts[0] += int(round(amount)) - sum(amounts)

    out = []
    for p, a in zip(picks, amounts):
        s = sleeves[p["i"]]
        current_pct = per[p["i"]] / total * 100 if total > 0 else 0.0
        out.append({
            "ticker": p["ticker"],
            "monto_usd": a,
            "grupo_id": s["id"],
            "grupo": s["grupo"],
            "nombre_grupo": s["nombre"],
            "actual_pct": round(current_pct, 1),
            "objetivo_pct": round(s["peso"], 1),
            "puntaje": ranking.get(p["ticker"]),
            "senal": signals.get(p["ticker"]),
            "falta_usd": round(p["gap"], 2),
        })
    return out


# ---------- puntaje de las apuestas temáticas ----------


def percentiles(values: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    known = {k: v for k, v in values.items() if v is not None}
    if not known:
        return {k: None for k in values}
    if len(known) == 1:
        return {k: (50.0 if k in known else None) for k in values}
    ordered = sorted(known.values())
    n = len(ordered)

    def rank(v):
        lo = sum(1 for x in ordered if x < v)
        eq = sum(1 for x in ordered if x == v)
        return (lo + (eq - 1) / 2) / (n - 1) * 100
    return {k: (round(rank(v), 1) if v is not None else None) for k, v in values.items()}


WEIGHTS = {"momentum": 0.3, "fundamental": 0.3, "tecnico": 0.2, "sentimiento": 0.2}


def momentum_12_1(closes: List[float]) -> Optional[float]:
    """Rendimiento de los últimos 12 meses sin el último mes (indicador clásico de tendencia)."""
    if len(closes) < 200:
        return None
    start, end = closes[0], closes[-22]
    return end / start - 1 if start > 0 else None


def composite_scores(cands: Dict[str, dict]) -> Dict[str, dict]:
    """cands[t] = {momentum, tecnico_puntaje, crecimiento, margen, moneda, sentimiento}. Devuelve puntaje 0-100."""
    mom = percentiles({t: c.get("momentum") for t, c in cands.items()})
    growth = percentiles({t: (c.get("crecimiento") if str(c.get("moneda", "USD")).upper().startswith("USD") else None)
                          for t, c in cands.items()})
    margin = percentiles({t: c.get("margen") for t, c in cands.items()})
    out = {}
    for t, c in cands.items():
        tech = c.get("tecnico_puntaje")
        fund_parts = [x for x in (growth[t], margin[t]) if x is not None]
        comps = {
            "momentum": mom[t],
            "fundamental": round(sum(fund_parts) / len(fund_parts), 1) if fund_parts else None,
            "tecnico": None if tech is None else round(min(max((tech + 5) / 10 * 100, 0), 100), 1),
            "sentimiento": c.get("sentimiento"),
        }
        w = {k: WEIGHTS[k] for k, v in comps.items() if v is not None}
        score = round(sum(comps[k] * w[k] for k in w) / sum(w.values()), 1) if w else None
        out[t] = {"puntaje": score, "componentes": comps}
    return out
