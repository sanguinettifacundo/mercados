"""Controla que recomendaciones.json y resumen.json estén bien antes de publicarlos.

Lo usa la tarea de publicación automática. Sale con error si algo no cumple las reglas.
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
errores = []


def cargar(nombre):
    try:
        with open(os.path.join(BASE, nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        errores.append(f"{nombre}: no es un JSON válido ({e})")
        return None


r = cargar("recomendaciones.json")
s = cargar("resumen.json")

if isinstance(r, dict):
    for clave in ["revision", "mercado", "cartera", "riesgo_retorno", "nucleo", "ideas", "tacticas", "cambios"]:
        if clave not in r:
            errores.append(f"recomendaciones.json: falta '{clave}'")
    cartera = r.get("cartera", [])
    total = sum(c.get("pct", 0) for c in cartera)
    if abs(total - 100) > 0.01:
        errores.append(f"La cartera suma {total}%, no 100%")
    ideas_pct = next((c["pct"] for c in cartera if "idea" in c.get("bloque", "").lower()), None)
    ideas = r.get("ideas", [])
    suma_ideas = sum(i.get("peso", 0) for i in ideas)
    if ideas_pct is not None and abs(suma_ideas - ideas_pct) > 0.01:
        errores.append(f"Las ideas suman {suma_ideas}% pero el bloque de ideas es {ideas_pct}%")
    if any(i.get("peso", 0) > 2.5 for i in ideas):
        errores.append("Ninguna idea puede pesar más de 2,5%")
    rr = r.get("riesgo_retorno", [])
    caida = sum(x["pct"] * x["caida"] / 100 for x in rr)
    if caida < -37:
        errores.append(f"El peor año estimado ({caida:.1f}%) supera el límite de -35% (tolerancia -37%)")
    if abs(sum(x["pct"] for x in rr) - 100) > 0.01:
        errores.append("riesgo_retorno no suma 100%")
    for t in r.get("tacticas", []):
        if not (t["stop"] < t["entrada"][0] <= t["entrada"][1] < t["obj"][0] <= t["obj"][1]):
            errores.append(f"Niveles incoherentes en la táctica {t.get('nombre')}")
elif r is not None:
    errores.append("recomendaciones.json debe ser un objeto")

if isinstance(s, list):
    for i, x in enumerate(s):
        for clave in ["fecha", "titulo", "texto", "impacto"]:
            if clave not in x:
                errores.append(f"resumen.json[{i}]: falta '{clave}'")
    if len(s) > 60:
        errores.append("resumen.json tiene más de 60 entradas: recortá las más viejas")
elif s is not None:
    errores.append("resumen.json debe ser una lista")

if errores:
    print("ERRORES:", *errores, sep="\n- ")
    sys.exit(1)
print("Todo en orden.")
