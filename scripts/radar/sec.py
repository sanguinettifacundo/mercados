"""Datos fundamentales gratuitos de la SEC (EE.UU.): ingresos, ganancia y ganancia por acción.

La SEC pide identificarse con un email de contacto (secreto SEC_CONTACTO).
Cubre empresas que presentan balances en EE.UU., incluidas varias argentinas que cotizan allá.
Los ETFs no tienen estos datos.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import date
from typing import Optional

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

REVENUE = {
    "us-gaap": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "ifrs-full": ["Revenue", "RevenueFromContractsWithCustomers"],
}
NET_INCOME = {
    "us-gaap": ["NetIncomeLoss", "ProfitLoss"],
    "ifrs-full": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
}
EPS = {
    "us-gaap": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "ifrs-full": ["DilutedEarningsPerShare", "BasicEarningsPerShare"],
}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}


class SecClient:
    def __init__(self, contact: str, pause: float = 0.15):
        self.ua = f"RadarBursatil/1.0 ({contact})"
        self.pause = pause
        self._map: Optional[dict] = None

    def _get(self, url: str) -> dict:
        req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        time.sleep(self.pause)
        return data

    def cik(self, ticker: str) -> Optional[int]:
        if self._map is None:
            raw = self._get(TICKERS_URL)
            self._map = {str(v["ticker"]).upper(): int(v["cik_str"]) for v in raw.values()}
        # La SEC usa guion donde Yahoo usa punto o guion (BRK-B / BRK.B).
        t = ticker.upper()
        return self._map.get(t) or self._map.get(t.replace("-", ".")) or self._map.get(t.replace(".", "-"))

    def fundamentals(self, ticker: str, price: Optional[float]) -> Optional[dict]:
        try:
            cik = self.cik(ticker)
            if not cik:
                return None
            return extract(self._get(FACTS_URL.format(cik=cik)), price)
        except Exception:  # noqa: BLE001
            return None


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def annual_series(facts: dict, tags: dict, unit_prefix: Optional[str] = None) -> tuple[list, str]:
    """Devuelve ([(fin, valor)] ordenado, unidad) del concepto con datos anuales más recientes."""
    best, best_unit = [], ""
    for taxonomy, names in tags.items():
        for name in names:
            concept = (facts.get(taxonomy) or {}).get(name)
            if not concept:
                continue
            for unit, entries in (concept.get("units") or {}).items():
                if unit_prefix and not unit.startswith(unit_prefix) and "/shares" not in unit:
                    continue
                by_end = {}
                for e in entries:
                    if e.get("form") not in ANNUAL_FORMS or not e.get("start") or not e.get("end"):
                        continue
                    if not 330 <= _days(e["start"], e["end"]) <= 400:
                        continue
                    prev = by_end.get(e["end"])
                    if prev is None or (e.get("filed") or "") > (prev.get("filed") or ""):
                        by_end[e["end"]] = e
                series = sorted(((end, float(v["val"])) for end, v in by_end.items()), key=lambda x: x[0])
                if series and (not best or series[-1][0] > best[-1][0]):
                    best, best_unit = series, unit
    return best, best_unit


def extract(companyfacts: dict, price: Optional[float]) -> Optional[dict]:
    facts = companyfacts.get("facts") or {}
    rev, rev_unit = annual_series(facts, REVENUE)
    if not rev:
        return None
    ni, _ = annual_series(facts, NET_INCOME)
    eps, eps_unit = annual_series(facts, EPS, unit_prefix=None)

    end, revenue = rev[-1]
    growth = None
    if len(rev) >= 2:
        prev_end, prev_rev = rev[-2]
        if 330 <= _days(prev_end, end) <= 400 and prev_rev > 0:
            growth = revenue / prev_rev - 1
    ni_by_end = dict(ni)
    margin = ni_by_end[end] / revenue if end in ni_by_end and revenue else None
    eps_by_end = dict(eps)
    eps_val = eps_by_end.get(end)
    pe = None
    if price and eps_val and eps_val > 0 and eps_unit.upper().startswith("USD"):
        pe = price / eps_val
    return {
        "empresa": companyfacts.get("entityName"),
        "ejercicio": end,
        "moneda": rev_unit,
        "ingresos": revenue,
        "crecimiento_ingresos_pct": None if growth is None else round(growth * 100, 1),
        "margen_neto_pct": None if margin is None else round(margin * 100, 1),
        "ganancia_por_accion": eps_val,
        "precio_ganancia": None if pe is None else round(pe, 1),
    }
