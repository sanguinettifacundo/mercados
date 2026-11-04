"""Cliente mínimo del endpoint público de gráficos de Yahoo Finance (datos con demora)."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Optional

HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_chart(symbol: str, payload: dict) -> Optional[dict]:
    results = (payload.get("chart") or {}).get("result") or []
    if not results:
        return None
    r = results[0]
    meta = r.get("meta") or {}
    ind = r.get("indicators") or {}
    quote = (ind.get("quote") or [{}])[0] or {}
    adj_block = (ind.get("adjclose") or [{}])[0] or {}
    raw_close = quote.get("close") or []
    raw_adj = adj_block.get("adjclose") or []
    stamps = r.get("timestamp") or []

    closes, adj, times = [], [], []
    for i, c in enumerate(raw_close):
        if c is None or c <= 0:
            continue
        a = raw_adj[i] if i < len(raw_adj) and raw_adj[i] and raw_adj[i] > 0 else c
        closes.append(float(c))
        adj.append(float(a))
        times.append(stamps[i] if i < len(stamps) else None)

    price = meta.get("regularMarketPrice")
    if not price or price <= 0:
        if not closes:
            return None
        price = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else None
    name = (meta.get("shortName") or meta.get("longName") or symbol).strip()
    return {
        "symbol": symbol,
        "name": name,
        "currency": meta.get("currency") or "",
        "price": float(price),
        "previous_close": prev,
        "change_pct": (float(price) - prev) / prev * 100.0 if prev else None,
        "closes": closes,
        "adj_closes": adj,
        "timestamps": times,
    }


def fetch(symbol: str, range_: str = "1y", interval: str = "1d", pause: float = 0.25) -> Optional[dict]:
    """Devuelve los datos o None si Yahoo no tiene el instrumento o falla la conexión."""
    s = urllib.parse.quote(symbol, safe="")
    for host in HOSTS:
        url = (
            f"https://{host}/v8/finance/chart/{s}?range={range_}&interval={interval}"
            "&includePrePost=false&events=div%2Csplit"
        )
        try:
            data = parse_chart(symbol, _get(url))
            time.sleep(pause)
            if data:
                return data
        except Exception:  # noqa: BLE001 - se prueba el otro host
            time.sleep(pause)
    return None
