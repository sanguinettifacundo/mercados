"""Estadísticas históricas sobre precios (idealmente ajustados por dividendos)."""
from __future__ import annotations

import math
from typing import List, Optional


def total_return(values: List[float]) -> Optional[float]:
    if len(values) < 2 or values[0] <= 0:
        return None
    return values[-1] / values[0] - 1.0


def cagr(values: List[float], periods_per_year: int) -> Optional[float]:
    if len(values) < 2 or values[0] <= 0 or values[-1] <= 0:
        return None
    years = (len(values) - 1) / periods_per_year
    if years <= 0:
        return None
    return (values[-1] / values[0]) ** (1.0 / years) - 1.0


def annual_volatility(values: List[float], periods_per_year: int) -> Optional[float]:
    if len(values) < 3:
        return None
    rets = [values[i] / values[i - 1] - 1.0 for i in range(1, len(values)) if values[i - 1] > 0]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(periods_per_year)


def max_drawdown(values: List[float]) -> Optional[float]:
    """Peor caída desde un máximo previo, como número negativo (-0.25 = -25 %)."""
    if len(values) < 2:
        return None
    peak, worst = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1.0)
    return worst
