"""Revisión mensual opcional con IA: tesis de cada apuesta temática y control del aporte sugerido.

Las instrucciones se publican también en docs/data/prompt.json para que las preguntas
que se hacen desde la web sigan las mismas reglas.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

VERDICTS = ("reforzar", "mantener", "vigilar", "salir", "evitar")

SCHEMA = """{
  "resumen": "3 a 5 oraciones: cómo está el plan, qué cambió en el mes y qué conviene hacer",
  "aporte": {"de_acuerdo": true, "comentario": "si el aporte sugerido por las reglas tiene sentido este mes o qué cambiarías y por qué"},
  "tesis": [
    {
      "ticker": "NVDA",
      "veredicto": "reforzar | mantener | vigilar | salir | evitar",
      "tesis": "por qué tener (o no) esta empresa a 20 años, en 2 o 3 oraciones",
      "fundamentos": "valuación, crecimiento, márgenes, deuda, con datos verificados",
      "sentimiento": "qué dicen las noticias, los analistas y los movimientos de directivos",
      "fusiones": "fusiones, adquisiciones o compras posibles o en curso; 'sin novedades' si no hay",
      "patentes": "patentes, aprobaciones regulatorias o productos en desarrollo relevantes; 'no aplica' si no corresponde",
      "riesgos": "qué rompería la tesis"
    }
  ],
  "alertas": ["hechos concretos que el inversor debería mirar este mes"],
  "proximos_eventos": ["presentaciones de resultados, decisiones regulatorias, etc., con fecha si se conoce"]
}"""

SYSTEM_TEMPLATE = """Sos un analista de inversiones de largo plazo que acompaña a un inversor argentino que invierte en dólares todos los meses. Respondés en español rioplatense, claro y concreto. Hoy es {hoy}.

El inversor usa un plan con reglas fijas: un núcleo de ETFs amplios (70 a 80 %) y apuestas temáticas en acciones (20 a 30 %). Cada mes las reglas eligen en qué poner el aporte según qué grupo está más atrasado y qué candidato tiene mejor puntaje (tendencia, técnico, fundamentos y sentimiento de noticias). Tu trabajo es revisar con criterio lo que las reglas no ven bien.

Cómo trabajás:
1. Para cada candidato temático y cada acción que el inversor ya tiene, evaluás la tesis a largo plazo combinando análisis fundamental, técnico, historial, sentimiento de mercado, fusiones y adquisiciones, y patentes o aprobaciones regulatorias cuando aplican.
2. Usás la búsqueda web para verificar datos actuales. No inventás cifras: si no pudiste verificar algo, lo decís.
3. Pensás a 20 años: no recomendás vender por ruido de corto plazo. "salir" es solo para tesis rotas (fraude, pérdida estructural de mercado, deterioro grave de fundamentos).
4. Respetás que el inversor tolera caídas de hasta el porcentaje indicado y que aporta montos chicos, por lo que conviene concentrar cada aporte en uno o dos instrumentos.
5. No prometés rendimientos. Aclarás brevemente que es un análisis automatizado, no asesoramiento profesional.

Formato de respuesta: podés escribir antes un comentario breve (máximo 5 oraciones), pero terminás SIEMPRE con un único bloque ```json con este esquema exacto:
""" + SCHEMA

FOLLOWUP_TEMPLATE = """Sos el analista de inversiones de largo plazo que acompaña a este inversor argentino que invierte en dólares todos los meses. Respondés en español rioplatense, claro y concreto. Hoy es {hoy}.
Abajo tenés su plan, su cartera y la última revisión. Respondé su pregunta. Usá la búsqueda web si hace falta un dato actual. No inventes cifras ni prometas rendimientos. Pensá a largo plazo."""


def today_text(d: Optional[date] = None) -> str:
    d = d or date.today()
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def system_prompt(d: Optional[date] = None) -> str:
    return SYSTEM_TEMPLATE.replace("{hoy}", today_text(d))


def build_review_request(profile: dict, plan_state: dict, ideas: list, holdings: list, suggestion: list) -> str:
    def j(x):
        return json.dumps(x, ensure_ascii=False)

    compact_ideas = []
    for i in ideas:
        compact_ideas.append({
            "ticker": i["ticker"], "grupo": i["grupo"], "nombre": i.get("nombre"),
            "puntaje": i.get("puntaje"), "componentes": i.get("componentes"),
            "senal": (i.get("senal") or {}).get("accion"),
            "rend_1a_pct": i.get("rend_1a_pct"), "rend_anual_5a_pct": i.get("rend_anual_5a_pct"),
            "caida_maxima_pct": i.get("caida_maxima_pct"),
            "fundamentos": i.get("fundamentos"),
            "patentes": i.get("patentes"),
            "titulares": [n["titulo"] for n in (i.get("noticias") or [])[:6]],
            "fusiones": [n["titulo"] for n in (i.get("sentimiento") or {}).get("fusiones", [])],
        })
    return "\n".join([
        "Perfil del inversor:", j(profile), "",
        "Distribución objetivo y situación actual por grupo:", j(plan_state), "",
        "Cartera real:", j(holdings), "",
        f"Aporte sugerido por las reglas para este mes (US$ {profile.get('aporte_mensual_usd')}):", j(suggestion), "",
        "Candidatos temáticos con los datos que calculó la plataforma:", j(compact_ideas), "",
        "Revisá cada candidato y cada acción de la cartera, decime si el aporte sugerido tiene sentido y qué tengo que mirar este mes.",
    ])


_FENCE = re.compile(r"```(?:json|JSON)?\s*\n?(\{[\s\S]*?\})\s*```")


def extract_json(text: str) -> Optional[str]:
    matches = list(_FENCE.finditer(text))
    if matches:
        return matches[-1].group(1)
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else None


def explanation(text: str) -> str:
    matches = list(_FENCE.finditer(text))
    if matches:
        m = matches[-1]
        return (text[:m.start()] + text[m.end():]).strip()
    start, end = text.find("{"), text.rfind("}")
    return (text[:start] + text[end + 1:]).strip() if 0 <= start < end else text.strip()


def parse_review(text: str) -> Optional[dict]:
    raw = extract_json(text)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tesis"), list):
        return None
    clean = []
    for t in data["tesis"]:
        if not isinstance(t, dict) or not t.get("ticker"):
            continue
        t["ticker"] = str(t["ticker"]).strip().upper()
        v = str(t.get("veredicto", "")).strip().lower()
        t["veredicto"] = v if v in VERDICTS else "mantener"
        clean.append(t)
    data["tesis"] = clean
    data.setdefault("alertas", [])
    data.setdefault("proximos_eventos", [])
    return data
