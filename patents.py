"""Patentes otorgadas en EE.UU. por empresa (PatentsView, gratis con clave: secreto PATENTSVIEW_API_KEY).

Compara las patentes de los últimos 12 meses con los 12 anteriores. Es un indicador
de actividad de innovación, no de calidad: la revisión con IA puede interpretarlo mejor.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Optional

URL = "https://search.patentsview.org/api/v1/patent/"


def _query(org: str, start: str, end: str, field: str) -> dict:
    return {
        "q": {"_and": [
            {"_gte": {"patent_date": start}},
            {"_lt": {"patent_date": end}},
            {"_text_phrase": {field: org}},
        ]},
        "f": ["patent_id"],
        "o": {"size": 1},
    }


def _count(api_key: str, org: str, start: str, end: str) -> Optional[int]:
    for field in ("assignees.assignee_organization", "assignee_organization"):
        body = json.dumps(_query(org, start, end, field)).encode("utf-8")
        req = urllib.request.Request(URL, data=body, method="POST",
                                     headers={"X-Api-Key": api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            time.sleep(1.5)  # límite de 45 pedidos por minuto
            total = data.get("total_hits")
            if isinstance(total, int):
                return total
        except urllib.error.HTTPError as e:
            time.sleep(1.5)
            if e.code == 400:
                continue  # probar con el otro nombre de campo
            return None
        except Exception:  # noqa: BLE001
            return None
    return None


def activity(api_key: str, org: str, today: Optional[date] = None) -> Optional[dict]:
    today = today or date.today()
    a = (today - timedelta(days=365)).isoformat()
    b = (today - timedelta(days=730)).isoformat()
    t = today.isoformat()
    recent = _count(api_key, org, a, t)
    if recent is None:
        return None
    before = _count(api_key, org, b, a)
    change = None if not before else round((recent / before - 1) * 100, 1)
    return {"ultimos_12_meses": recent, "12_meses_previos": before, "variacion_pct": change}
