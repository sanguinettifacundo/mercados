"""Actualiza asesor/data.json con datos de mercado del día.

Lo corre la tarea programada de GitHub Actions (.github/workflows/asesor-diario.yml).
Solo usa la biblioteca estándar de Python. Si una fuente falla, conserva el dato anterior.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

RUTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
ART = timezone(timedelta(hours=-3))
UA = {"User-Agent": "Mozilla/5.0 (asesor-diario)"}

# Instrumentos con señales técnicas: símbolo de Yahoo -> nombre visible
INSTRUMENTOS = {
    "^GSPC": "S&P 500 (índice)",
    "SPY": "SPY · S&P 500",
    "EFA": "EFA · Países desarrollados",
    "YPF": "YPF (ADR)",
    "GGAL": "Grupo Galicia (ADR)",
    "PAM": "Pampa Energía (ADR)",
    "VIST": "Vista Energy",
    "BZ=F": "Petróleo Brent",
}

# Operaciones tácticas: símbolo, zona de entrada, stop y objetivos
TACTICAS = [
    {"nombre": "YPF (ADR)", "simbolo": "YPF", "entrada": [32.5, 34], "stop": 30.5, "obj": [38.5, 43.5]},
    {"nombre": "GGAL (ADR)", "simbolo": "GGAL", "entrada": [25.5, 27], "stop": 24, "obj": [29.5, 33]},
    {"nombre": "CEDEAR SPY (nivel del S&P 500)", "simbolo": "^GSPC", "entrada": [6950, 7150], "stop": 6750, "obj": [7500, 7750]},
]


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None


def rsi(v, n=14):
    if len(v) <= n:
        return None
    gan = per = 0.0
    for i in range(1, n + 1):
        d = v[i] - v[i - 1]
        gan += max(d, 0)
        per += max(-d, 0)
    gan /= n
    per /= n
    for i in range(n + 1, len(v)):
        d = v[i] - v[i - 1]
        gan = (gan * (n - 1) + max(d, 0)) / n
        per = (per * (n - 1) + max(-d, 0)) / n
    if per == 0:
        return 100.0
    return 100 - 100 / (1 + gan / per)


def analizar(cierres, fechas):
    """Señales técnicas a partir de una serie de cierres diarios."""
    ult = cierres[-1]
    ant = cierres[-2] if len(cierres) > 1 else ult
    s50, s200, r = sma(cierres, 50), sma(cierres, 200), rsi(cierres)
    maximo = max(cierres)
    minimo = min(cierres)
    if s50 and s200:
        if ult > s50 > s200:
            tend = "Alcista"
        elif ult < s50 < s200:
            tend = "Bajista"
        else:
            tend = "Lateral"
    else:
        tend = "Sin datos"
    if r is None:
        lectura = ""
    elif r >= 70:
        lectura = "Sobrecompra"
    elif r <= 30:
        lectura = "Sobreventa"
    else:
        lectura = "Neutral"
    return {
        "precio": round(ult, 2),
        "var_dia": round((ult / ant - 1) * 100, 2),
        "max_52s": round(maximo, 2),
        "min_52s": round(minimo, 2),
        "dist_max": round((ult / maximo - 1) * 100, 1),
        "sma50": round(s50, 2) if s50 else None,
        "sma200": round(s200, 2) if s200 else None,
        "rsi": round(r, 1) if r is not None else None,
        "rsi_lectura": lectura,
        "tendencia": tend,
        "fecha": fechas[-1],
    }


def yahoo(simbolo):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.request.quote(simbolo) + "?range=1y&interval=1d")
    res = get_json(url)["chart"]["result"][0]
    ts = res["timestamp"]
    cl = res["indicators"]["quote"][0]["close"]
    pares = [(t, c) for t, c in zip(ts, cl) if c is not None]
    cierres = [c for _, c in pares]
    fechas = [datetime.fromtimestamp(t, ART).strftime("%Y-%m-%d") for t, _ in pares]
    return analizar(cierres, fechas)


def estado_tactica(t, precio):
    lo, hi = t["entrada"]
    if precio is None:
        return "Sin dato", "w"
    if precio <= t["stop"]:
        return "Perforó el stop: operación descartada", "b"
    if precio >= t["obj"][1]:
        return "Llegó al objetivo 2", "g"
    if precio >= t["obj"][0]:
        return "Llegó al objetivo 1", "g"
    if lo <= precio <= hi:
        return "Dentro de la zona de entrada", "g"
    if precio > hi:
        return "Encima de la zona: esperar", "w"
    return "Debajo de la zona, sobre el stop: esperar confirmación", "w"


def main():
    try:
        with open(RUTA, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    errores = []

    def intento(nombre, fn):
        try:
            fn()
        except Exception as e:  # una fuente caída no frena al resto
            errores.append(f"{nombre}: {e}")

    def dolares():
        mep = get_json("https://dolarapi.com/v1/dolares/bolsa")
        ccl = get_json("https://dolarapi.com/v1/dolares/contadoconliqui")
        data["mep"] = {"valor": mep["venta"], "fecha": mep.get("fechaActualizacion", "")[:10]}
        data["ccl"] = {"valor": ccl["venta"], "fecha": ccl.get("fechaActualizacion", "")[:10]}

    def riesgo():
        rp = get_json("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais/ultimo")
        data["riesgo_pais"] = {"valor": rp["valor"], "fecha": rp["fecha"][:10]}

    def inflacion():
        inf = get_json("https://api.argentinadatos.com/v1/finanzas/indices/inflacion")
        ult = inf[-1]
        data["inflacion"] = {"valor": ult["valor"], "fecha": ult["fecha"][:7]}

    intento("dólar", dolares)
    intento("riesgo país", riesgo)
    intento("inflación", inflacion)

    instr = data.get("instrumentos", {})
    for sim, nombre in INSTRUMENTOS.items():
        def f(sim=sim, nombre=nombre):
            d = yahoo(sim)
            d["nombre"] = nombre
            instr[sim] = d
        intento(sim, f)
    data["instrumentos"] = instr

    tact = []
    for t in TACTICAS:
        precio = instr.get(t["simbolo"], {}).get("precio")
        txt, nivel = estado_tactica(t, precio)
        tact.append({"nombre": t["nombre"], "precio": precio, "entrada": t["entrada"],
                     "stop": t["stop"], "obj": t["obj"], "estado": txt, "nivel": nivel})
    data["tacticas"] = tact

    data["actualizado"] = datetime.now(ART).strftime("%d/%m/%Y %H:%M")
    data["errores"] = errores
    with open(RUTA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("Actualizado.", "Errores:" if errores else "", *errores, sep="\n")
    # Falla solo si no se pudo obtener nada
    if len(errores) >= 3 + len(INSTRUMENTOS):
        sys.exit(1)


if __name__ == "__main__":
    main()
