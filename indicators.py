"""Indicadores técnicos clásicos sobre una serie de cierres.

Cada función devuelve una lista del mismo largo que la entrada, con None donde
todavía no hay datos suficientes.
"""
from __future__ import annotations

from typing import List, Optional

Series = List[Optional[float]]


def sma(values: List[float], period: int) -> Series:
    out: Series = [None] * len(values)
    if period <= 0:
        return out
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: List[float], period: int) -> Series:
    out: Series = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _to_rsi(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 50.0 if avg_gain == 0 else 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


def rsi(values: List[float], period: int = 14) -> Series:
    """RSI de Wilder (0 a 100)."""
    out: Series = [None] * len(values)
    if period <= 0 or len(values) <= period:
        return out
    gain = loss = 0.0
    for i in range(1, period + 1):
        d = values[i] - values[i - 1]
        if d >= 0:
            gain += d
        else:
            loss -= d
    avg_gain, avg_loss = gain / period, loss / period
    out[period] = _to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        d = values[i] - values[i - 1]
        g = d if d > 0 else 0.0
        l = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = _to_rsi(avg_gain, avg_loss)
    return out


def macd(values: List[float], fast: int = 12, slow: int = 26, signal_period: int = 9):
    """Devuelve (línea MACD, línea de señal, histograma)."""
    f, s = ema(values, fast), ema(values, slow)
    line: Series = [a - b if a is not None and b is not None else None for a, b in zip(f, s)]
    signal: Series = [None] * len(values)
    first = next((i for i, v in enumerate(line) if v is not None), None)
    if first is not None:
        compact = [v for v in line[first:]]  # sin None a partir de acá
        sig = ema(compact, signal_period)  # type: ignore[arg-type]
        for j, v in enumerate(sig):
            signal[first + j] = v
    hist: Series = [m - g if m is not None and g is not None else None for m, g in zip(line, signal)]
    return line, signal, hist
