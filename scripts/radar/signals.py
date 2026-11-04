"""Convierte una serie de cierres diarios en una señal de COMPRA, VENTA o MANTENER.

Puntaje:
  * Cruce de medias 20/50 en las últimas 3 ruedas: +2 (alcista) / -2 (bajista).
    Sin cruce reciente: +1 si la media de 20 está arriba de la de 50, -1 si está abajo.
  * RSI(14) menor a 30: +2 (sobreventa). Mayor a 70: -2 (sobrecompra).
  * MACD(12,26,9) que cruza su línea de señal en las últimas 2 ruedas: +1 / -1.

Puntaje >= 2: COMPRA. <= -2: VENTA. Si no: MANTENER.
"""
from __future__ import annotations

from typing import List, Optional

from . import indicators as ind

BUY, SELL, HOLD = "COMPRA", "VENTA", "MANTENER"
MIN_BARS = 60
CROSS_LOOKBACK = 3
MACD_LOOKBACK = 2


def recent_sign_change(series: List[Optional[float]], lookback: int) -> int:
    """+1 si la serie pasó de <=0 a >0 en las últimas `lookback` ruedas, -1 al revés, 0 si no."""
    last = len(series) - 1
    start = max(1, last - lookback + 1)
    for i in range(last, start - 1, -1):
        now, before = series[i], series[i - 1]
        if now is None or before is None:
            continue
        if before <= 0 < now:
            return 1
        if before >= 0 > now:
            return -1
    return 0


def recent_cross(fast, slow, lookback: int) -> int:
    diff = [a - b if a is not None and b is not None else None for a, b in zip(fast, slow)]
    return recent_sign_change(diff, lookback)


def evaluate(closes: List[float]) -> dict:
    if len(closes) < MIN_BARS:
        return {
            "accion": HOLD, "puntaje": 0, "rsi": None,
            "motivos": [f"Pocos datos históricos ({len(closes)} ruedas, se necesitan {MIN_BARS})"],
        }
    sma20, sma50 = ind.sma(closes, 20), ind.sma(closes, 50)
    rsi_series = ind.rsi(closes, 14)
    _, _, hist = ind.macd(closes)

    score = 0
    reasons: List[str] = []

    cross = recent_cross(sma20, sma50, CROSS_LOOKBACK)
    if cross > 0:
        score += 2
        reasons.append("Cruce alcista: la media de 20 ruedas pasó por encima de la de 50")
    elif cross < 0:
        score -= 2
        reasons.append("Cruce bajista: la media de 20 ruedas pasó por debajo de la de 50")
    else:
        a, b = sma20[-1], sma50[-1]
        if a is not None and b is not None:
            if a > b:
                score += 1
                reasons.append("Tendencia alcista (media 20 sobre media 50)")
            elif a < b:
                score -= 1
                reasons.append("Tendencia bajista (media 20 debajo de media 50)")

    r = rsi_series[-1]
    if r is not None:
        if r < 30:
            score += 2
            reasons.append(f"RSI {r:.0f}: sobreventa")
        elif r > 70:
            score -= 2
            reasons.append(f"RSI {r:.0f}: sobrecompra")
        else:
            reasons.append(f"RSI {r:.0f}: zona neutral")

    m = recent_sign_change(hist, MACD_LOOKBACK)
    if m > 0:
        score += 1
        reasons.append("MACD cruzó al alza su línea de señal")
    elif m < 0:
        score -= 1
        reasons.append("MACD cruzó a la baja su línea de señal")

    action = BUY if score >= 2 else SELL if score <= -2 else HOLD
    return {"accion": action, "puntaje": score, "rsi": r, "motivos": reasons}
