"""Proceso diario de Radar Bursátil (corre en GitHub Actions de lunes a viernes).

Gratis, sin IA:
  1. Cotizaciones de índices, de tu plan, de tu lista y de tu cartera real (Yahoo Finance).
  2. Historial y señales técnicas.
  3. Fundamentales (SEC), sentimiento y fusiones en noticias (Google Noticias) y patentes (PatentsView).
  4. Puntaje de cada candidato temático y rotación del aporte mensual.
  5. Avisos: recordatorio del aporte, señales, fusiones, tesis en riesgo y resumen.
Opcional, con IA (una vez por mes, si cargaste ANTHROPIC_API_KEY):
  6. Revisión de la tesis de cada apuesta y del aporte sugerido.

Secretos de GitHub que usa (todos opcionales):
  ANTHROPIC_API_KEY, SEC_CONTACTO, PATENTSVIEW_API_KEY, NTFY_TOPIC, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  FORCE_AI=true fuerza la revisión con IA; FORCE_REMINDER=true fuerza el recordatorio del aporte.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from radar import advisor, catalog, claude, news, notify, patents, plan, sec, signals, stats, yahoo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
CONFIG_PATH = ROOT / "config.json"
PORTFOLIO_PATH = ROOT / "cartera.json"
STATE_PATH = ROOT / "estado.json"

MESES = advisor.MESES


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def normalize(symbol: str) -> str:
    return str(symbol).strip().upper().replace(" ", "")


def truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "si", "sí", "yes")


def pct_text(v: Optional[float], signed: bool = True, decimals: int = 1) -> str:
    if v is None:
        return "s/d"
    sign = "+" if signed and v > 0 else ""
    return f"{sign}{v:.{decimals}f} %".replace(".", ",")


def money(v: Optional[float]) -> str:
    if v is None:
        return "s/d"
    return "US$ " + f"{v:,.0f}".replace(",", ".")


def site_url(config: dict) -> str:
    url = (config.get("avisos") or {}).get("url_web") or ""
    if url:
        return url
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner.lower()}.github.io/{name}/"
    return ""


def _pct(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v * 100, 2)


def suggestion_text(suggestion: list) -> str:
    if not suggestion:
        return "No hay sugerencia: revisá tu distribución en config.json."
    parts = []
    for s in suggestion:
        parts.append(f"{money(s['monto_usd'])} en {s['ticker']} ({s['nombre_grupo']}: "
                     f"{pct_text(s['actual_pct'], signed=False, decimals=0)} de {pct_text(s['objetivo_pct'], signed=False, decimals=0)} objetivo)")
    return "\n".join(parts)


def run(fetch=yahoo.fetch, ask=claude.ask, send=notify.send, news_fetch=news.fetch,
        sec_factory=sec.SecClient, patents_fn=patents.activity, today: Optional[datetime] = None) -> dict:
    today = today or datetime.now()
    config = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {})
    movements = (load_json(PORTFOLIO_PATH, {}) or {}).get("movimientos", [])
    errors: list[str] = []
    url = site_url(config)

    p = config.get("perfil") or {}
    profile = {
        "objetivo": p.get("objetivo", "Hacer crecer el capital"),
        "horizonte_anios": p.get("horizonte_anios", 20),
        "caida_tolerada_pct": p.get("caida_tolerada_pct", 35),
        "aporte_mensual_usd": float(p.get("aporte_mensual_usd", 100)),
        "objetivo_anual_usd_pct": float(p.get("objetivo_anual_usd_pct", 10)),
    }
    sleeves = plan.normalize_sleeves(config.get("distribucion") or [])
    watchlist = [normalize(s) for s in config.get("lista", []) if str(s).strip()]
    holdings = plan.holdings_from_movements(movements)

    # ---------- 1. Mercados ----------
    print("Mercados…", flush=True)
    markets = []
    for sym, name, region in catalog.MARKETS:
        d = fetch(sym, "1mo", "1d")
        markets.append({
            "symbol": sym, "name": name, "region": region,
            "price": d["price"] if d else None, "currency": d["currency"] if d else "",
            "change_pct": d["change_pct"] if d else None,
            "spark": [round(x, 4) for x in d["closes"][-30:]] if d else [],
        })
    write_json(DATA / "markets.json", markets)

    # ---------- 2. Cotizaciones, historial y señales ----------
    print("Historial y señales…", flush=True)
    tickers: list[str] = []
    for t in [c for s in sleeves for c in s["candidatos"]] + watchlist + list(holdings):
        if t not in tickers:
            tickers.append(t)
    assets: dict[str, dict] = {}
    for t in tickers:
        daily = fetch(t, "1y", "1d")
        weekly = fetch(t, "5y", "1wk")
        base = daily or weekly
        if not base:
            continue
        adj = weekly["adj_closes"] if weekly else []
        assets[t] = {
            "nombre": base["name"], "moneda": base["currency"], "precio": base["price"],
            "variacion_dia_pct": daily["change_pct"] if daily else None,
            "rend_1a_pct": _pct(stats.total_return(adj[-53:])) if adj else None,
            "rend_anual_5a_pct": _pct(stats.cagr(adj, 52)) if adj else None,
            "anios_de_datos": round(max(len(adj) - 1, 0) / 52, 1),
            "volatilidad_pct": _pct(stats.annual_volatility(adj, 52)) if adj else None,
            "caida_maxima_pct": _pct(stats.max_drawdown(adj)) if adj else None,
            "senal": signals.evaluate(daily["closes"]) if daily else None,
            "momentum": plan.momentum_12_1(daily["closes"]) if daily else None,
            "spark": [round(x, 4) for x in daily["closes"][-60:]] if daily else [],
        }
    prices = {t: a["precio"] for t, a in assets.items()}
    signal_map = {t: a["senal"]["accion"] for t, a in assets.items() if a.get("senal")}

    # ---------- 3. Cartera real ----------
    valued = plan.value_holdings(holdings, prices)
    values = {r["ticker"]: r["valor_usd"] for r in valued if r["valor_usd"] is not None}

    # ---------- 4. Ideas temáticas: fundamentales, noticias, patentes, puntaje ----------
    print("Fundamentales, noticias y patentes…", flush=True)
    sec_contact = os.environ.get("SEC_CONTACTO", "").strip()
    sec_client = sec_factory(sec_contact) if sec_contact else None
    pv_key = os.environ.get("PATENTSVIEW_API_KEY", "").strip()
    thematic = [s for s in sleeves if s["grupo"].lower() != "núcleo" and len(s["candidatos"]) > 0]
    ideas, cand_inputs = [], {}
    for s in thematic:
        for t in s["candidatos"]:
            a = assets.get(t)
            if not a:
                ideas.append({"ticker": t, "grupo": s["nombre"], "grupo_id": s["id"], "sin_datos": True})
                continue
            company = s["nombres"].get(t) or news.clean_company_name(a["nombre"])
            items = news_fetch(company) or []
            senti = news.summarize(items) if items else None
            fund = sec_client.fundamentals(t, a["precio"]) if sec_client else None
            pat = None
            if s["patentes"] and pv_key:
                pat = patents_fn(pv_key, s["titulares_patentes"].get(t) or company)
            cand_inputs[t] = {
                "momentum": a["momentum"],
                "tecnico_puntaje": (a["senal"] or {}).get("puntaje"),
                "crecimiento": (fund or {}).get("crecimiento_ingresos_pct"),
                "margen": (fund or {}).get("margen_neto_pct"),
                "moneda": (fund or {}).get("moneda", "USD"),
                "sentimiento": (senti or {}).get("puntaje"),
            }
            ideas.append({
                "ticker": t, "grupo": s["nombre"], "grupo_id": s["id"], "nombre": company,
                "precio": a["precio"], "moneda": a["moneda"], "variacion_dia_pct": a["variacion_dia_pct"],
                "rend_1a_pct": a["rend_1a_pct"], "rend_anual_5a_pct": a["rend_anual_5a_pct"],
                "volatilidad_pct": a["volatilidad_pct"], "caida_maxima_pct": a["caida_maxima_pct"],
                "momentum_pct": _pct(a["momentum"]),
                "senal": a["senal"], "fundamentos": fund, "patentes": pat,
                "sentimiento": senti, "noticias": items[:8],
                "en_cartera": t in holdings, "spark": a["spark"],
            })
    scores = plan.composite_scores(cand_inputs)
    for i in ideas:
        sc = scores.get(i["ticker"])
        if sc:
            i["puntaje"], i["componentes"] = sc["puntaje"], sc["componentes"]
    ranking = {t: sc["puntaje"] for t, sc in scores.items() if sc["puntaje"] is not None}

    # ---------- 5. Plan y aporte sugerido ----------
    suggestion = plan.suggest(sleeves, values, profile["aporte_mensual_usd"], ranking, signal_map)
    per, others = plan.sleeve_values(sleeves, values)
    total = sum(per) + others
    invested = sum(h["invertido_usd"] for h in holdings.values())
    plan_doc = {
        "generado": now_iso(),
        "perfil": profile,
        "grupos": [{
            "id": s["id"], "grupo": s["grupo"], "nombre": s["nombre"], "peso": s["peso"],
            "candidatos": s["candidatos"], "valor_usd": round(per[i], 2),
            "actual_pct": round(per[i] / total * 100, 1) if total > 0 else 0.0,
        } for i, s in enumerate(sleeves)],
        "otros_valor_usd": round(others, 2),
        "total_usd": round(total, 2),
        "invertido_usd": round(invested, 2),
        "resultado_usd": round(total - invested, 2) if valued else 0.0,
        "resultado_pct": round((total / invested - 1) * 100, 2) if invested else None,
        "cartera": valued,
        "movimientos": movements[-50:],
        "ranking": ranking,
        "senales": signal_map,
        "precios": prices,
        "nombres": {t: a["nombre"] for t, a in assets.items()},
        "sugerencia": suggestion,
    }
    write_json(DATA / "plan.json", plan_doc)
    write_json(DATA / "ideas.json", ideas)

    # ---------- 6. Señales de tu lista y tu cartera ----------
    tracked = []
    for t in list(holdings) + watchlist:
        if t not in tracked:
            tracked.append(t)
    signal_rows = []
    for t in tracked:
        a = assets.get(t)
        if not a or not a.get("senal"):
            signal_rows.append({"symbol": t, "sin_datos": True, "en_cartera": t in holdings, "en_lista": t in watchlist})
            continue
        signal_rows.append({
            "symbol": t, "nombre": a["nombre"], "moneda": a["moneda"], "precio": a["precio"],
            "variacion_dia_pct": a["variacion_dia_pct"], **a["senal"],
            "en_cartera": t in holdings, "en_lista": t in watchlist, "spark": a["spark"],
        })
    write_json(DATA / "signals.json", signal_rows)

    # ---------- 7. Revisión mensual con IA (opcional) ----------
    month_key = today.strftime("%Y-%m")
    reminder_day = int((config.get("avisos") or {}).get("dia_recordatorio", 1))
    reminder_due = truthy("FORCE_REMINDER") or (today.day >= reminder_day and state.get("recordatorio_mes") != month_key)
    ai_cfg = config.get("ia") or {}
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    ai_doc = load_json(DATA / "ai.json", None)
    ai_note = ""
    ai_due = truthy("FORCE_AI") or (reminder_due and state.get("ia_mes") != month_key)
    if not ai_cfg.get("activada", True):
        ai_note = "La revisión con IA está desactivada en config.json."
    elif not api_key:
        ai_note = "Modo gratuito: sin clave de la IA. Todo lo demás funciona igual."
    elif not ai_due:
        ai_note = "La IA revisa el plan una vez por mes, junto con el recordatorio del aporte."
    else:
        print("Revisión mensual con IA…", flush=True)
        try:
            plan_state = [{k: g[k] for k in ("grupo", "nombre", "peso", "actual_pct", "candidatos")} for g in plan_doc["grupos"]]
            answer = ask(api_key, advisor.system_prompt(today.date()),
                         advisor.build_review_request(profile, plan_state, ideas, valued, suggestion),
                         model=ai_cfg.get("modelo") or claude.DEFAULT_MODEL,
                         max_searches=int(ai_cfg.get("busquedas_max", 8)))
            review = advisor.parse_review(answer["text"])
            if review is None:
                raise ValueError("La IA respondió, pero sin una revisión legible. Se mantiene la anterior.")
            old = {t["ticker"]: t["veredicto"] for t in ((ai_doc or {}).get("revision") or {}).get("tesis", [])}
            ai_doc = {"creada": now_iso(), "modelo": ai_cfg.get("modelo") or claude.DEFAULT_MODEL,
                      "revision": review, "comentario": advisor.explanation(answer["text"]), "fuentes": answer["sources"]}
            write_json(DATA / "ai.json", ai_doc)
            state["ia_mes"] = month_key
            ai_note = "Revisión con IA de este mes lista."
            for th in review["tesis"]:
                if th["ticker"] in holdings and th["veredicto"] in ("salir", "vigilar") and old.get(th["ticker"]) != th["veredicto"]:
                    errors += send(f"La IA sugiere {th['veredicto']}: {th['ticker']}",
                                   f"{th.get('tesis', '')}\nRiesgo: {th.get('riesgos', '')}", url, ["warning"], 4)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            errors.append(f"IA: {e}")
            ai_note = f"No se pudo hacer la revisión con IA: {e}"

    # ---------- 8. Avisos ----------
    if reminder_due:
        month_name = MESES[today.month - 1]
        body = (f"Con {money(profile['aporte_mensual_usd'])} este mes, el plan sugiere:\n{suggestion_text(suggestion)}")
        ai_ok = ((ai_doc or {}).get("revision") or {}).get("aporte") if state.get("ia_mes") == month_key else None
        if ai_ok and ai_ok.get("comentario"):
            body += f"\nIA: {ai_ok['comentario']}"
        body += "\nSi aportás otro monto, abrí la web: recalcula al instante. Después registrá la compra."
        errors += send(f"Aporte de {month_name}", body, url, ["moneybag"], 4)
        state["recordatorio_mes"] = month_key

    last = state.get("ultimas_senales", {})
    for r in signal_rows:
        if r.get("sin_datos") or r["accion"] == signals.HOLD or last.get(r["symbol"]) == r["accion"]:
            continue
        where = " (en tu cartera)" if r["en_cartera"] else ""
        body = (f"{r['precio']:.2f} {r['moneda']} ({pct_text(r['variacion_dia_pct'], decimals=2)})\n"
                + "\n".join(f"• {m}" for m in r["motivos"])
                + "\nSeñal técnica de corto plazo: para un plan a 20 años, no es motivo de venta por sí sola.")
        tags = ["chart_with_upwards_trend"] if r["accion"] == signals.BUY else ["chart_with_downwards_trend"]
        errors += send(f"{r['accion']}: {r['symbol']}{where}", body, url, tags, 3)
    state["ultimas_senales"] = {r["symbol"]: r["accion"] for r in signal_rows if not r.get("sin_datos")}

    seen = state.get("fusiones_vistas", [])
    seen_set = set(seen)
    for i in ideas:
        news_ma = [n for n in ((i.get("sentimiento") or {}).get("fusiones") or []) if n["url"] not in seen_set]
        if news_ma and (i.get("en_cartera") or (i.get("puntaje") or 0) >= 50):
            body = "\n".join(f"• {n['titulo']} ({n['medio']})" for n in news_ma[:3])
            errors += send(f"Posible fusión o adquisición: {i['ticker']}", body, url, ["handshake"], 3)
        for n in news_ma:
            seen.append(n["url"])
            seen_set.add(n["url"])
    state["fusiones_vistas"] = seen[-400:]

    alerts = state.get("tesis_en_riesgo", {})
    for i in ideas:
        if not i.get("en_cartera") or i.get("sin_datos"):
            continue
        senti = (i.get("sentimiento") or {}).get("puntaje")
        at_risk = (i.get("senal") or {}).get("accion") == signals.SELL and senti is not None and senti < 40
        if at_risk and not alerts.get(i["ticker"]):
            errors += send(f"Revisá tu tesis: {i['ticker']}",
                           "Tiene señal técnica de venta y noticias mayormente negativas. "
                           "No es motivo para vender, pero conviene leer qué está pasando.", url, ["mag"], 3)
        alerts[i["ticker"]] = at_risk
    state["tesis_en_riesgo"] = alerts

    freq = str((config.get("avisos") or {}).get("resumen", "semanal")).lower()
    if freq == "diario" or (freq == "semanal" and today.weekday() == 4):
        errors += send("Resumen de tu plan", summary_text(plan_doc, signal_rows), url, ["bar_chart"], 2)

    # ---------- 9. Metadatos ----------
    state["ultima_ejecucion"] = now_iso()
    write_json(STATE_PATH, state)
    write_json(DATA / "prompt.json", {"seguimiento": advisor.FOLLOWUP_TEMPLATE,
                                      "modelo": ai_cfg.get("modelo") or claude.DEFAULT_MODEL})
    meta = {
        "actualizado": now_iso(),
        "ia": ai_note,
        "fuentes": {"sec": bool(sec_client), "patentes": bool(pv_key), "ia": bool(api_key)},
        "avisos": notify.channels(),
        "errores": errors,
        "lista": watchlist,
        "repositorio": os.environ.get("GITHUB_REPOSITORY", ""),
    }
    write_json(DATA / "meta.json", meta)
    print("Listo.", json.dumps({"errores": errors, "ia": ai_note}, ensure_ascii=False), flush=True)
    return meta


def summary_text(plan_doc: dict, rows: list) -> str:
    lines = []
    if plan_doc["cartera"]:
        lines.append(f"Tu cartera: {money(plan_doc['total_usd'])} "
                     f"({pct_text(plan_doc['resultado_pct'])} sobre lo invertido).")
    behind = sorted(plan_doc["grupos"], key=lambda g: g["actual_pct"] - g["peso"])[:1]
    if behind and plan_doc["total_usd"] > 0:
        g = behind[0]
        lines.append(f"Más atrasado: {g['nombre']} ({pct_text(g['actual_pct'], signed=False, decimals=0)} "
                     f"de {pct_text(g['peso'], signed=False, decimals=0)}).")
    if plan_doc["sugerencia"]:
        lines.append("Próximo aporte: " + ", ".join(f"{s['ticker']} {money(s['monto_usd'])}" for s in plan_doc["sugerencia"]) + ".")
    ok = [r for r in rows if not r.get("sin_datos")]
    sells = [r["symbol"] for r in ok if r["accion"] == signals.SELL]
    buys = [r["symbol"] for r in ok if r["accion"] == signals.BUY]
    if buys or sells:
        lines.append(f"Señales: compra {', '.join(buys) or 'ninguna'}; venta {', '.join(sells) or 'ninguna'}.")
    return "\n".join(lines) or "Sin novedades esta semana."


if __name__ == "__main__":
    run()
