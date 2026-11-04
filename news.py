"""Noticias gratuitas (Google Noticias por RSS): sentimiento aproximado y menciones de fusiones.

No usa IA: cuenta palabras positivas y negativas en los titulares. Es una medida
aproximada; la revisión mensual con IA, si está activada, lee las noticias con más criterio.
"""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import List, Optional

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) RadarBursatil/1.0"

POSITIVE = [
    "beat", "beats", "tops estimates", "surge", "surges", "soar", "soars", "jump", "jumps", "rally", "rallies",
    "record high", "record revenue", "upgrade", "upgraded", "outperform", "buy rating", "raises guidance",
    "raised guidance", "raises outlook", "strong demand", "bullish", "approval", "approved", "approves",
    "breakthrough", "wins", "partnership", "expands", "expansion", "profit rises", "growth accelerates",
]
NEGATIVE = [
    "miss", "misses", "plunge", "plunges", "tumble", "tumbles", "slump", "slumps", "sinks", "falls",
    "drops", "downgrade", "downgraded", "underperform", "sell rating", "cuts guidance", "cut guidance",
    "lowers outlook", "lawsuit", "sued", "probe", "investigation", "recall", "fraud", "loss widens",
    "weak demand", "bearish", "layoffs", "job cuts", "warning", "halts", "fined", "rejects", "rejected",
    "delay", "delays", "antitrust", "default",
]
MERGER = [
    "acquire", "acquires", "acquiring", "acquisition", "acquired by", "merger", "merge with", "merges with",
    "takeover", "buyout", "deal to buy", "agrees to buy", "offer to buy", "bid for", "tender offer", "in talks to buy",
]


def _pattern(words: List[str]) -> re.Pattern:
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.I)


_POS, _NEG, _MA = _pattern(POSITIVE), _pattern(NEGATIVE), _pattern(MERGER)


def score_headline(title: str) -> int:
    """+1 positivo, -1 negativo, 0 neutro."""
    p, n = len(_POS.findall(title)), len(_NEG.findall(title))
    return (p > n) - (n > p)


def mentions_merger(title: str) -> bool:
    return bool(_MA.search(title))


def parse_rss(xml_text: str, limit: int = 20) -> List[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        source = (it.findtext("source") or "").strip()
        # Google Noticias agrega " - Medio" al final del título.
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        date_iso = None
        raw = it.findtext("pubDate")
        if raw:
            try:
                date_iso = parsedate_to_datetime(raw).date().isoformat()
            except (TypeError, ValueError):
                pass
        items.append({
            "titulo": title,
            "url": (it.findtext("link") or "").strip(),
            "medio": source,
            "fecha": date_iso,
            "tono": score_headline(title),
            "fusion": mentions_merger(title),
        })
        if len(items) >= limit:
            break
    return items


def summarize(items: List[dict]) -> dict:
    pos = sum(1 for i in items if i["tono"] > 0)
    neg = sum(1 for i in items if i["tono"] < 0)
    value = (pos - neg) / (pos + neg + 2)  # entre -1 y 1, prudente con pocas noticias
    return {
        "positivas": pos, "negativas": neg, "total": len(items),
        "puntaje": round(50 + 50 * value, 1),
        "fusiones": [i for i in items if i["fusion"]][:5],
    }


def search_query(company: str) -> str:
    return f'"{company}" stock when:30d'


def fetch(company: str, limit: int = 20, pause: float = 0.5) -> Optional[List[dict]]:
    q = urllib.parse.quote(search_query(company))
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        time.sleep(pause)
        return parse_rss(text, limit)
    except Exception:  # noqa: BLE001
        return None


_SUFFIXES = re.compile(r"[,.]?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|s\.?a\.?|n\.?v\.?|holdings?|group|class [a-c])\.?$", re.I)


def clean_company_name(name: str) -> str:
    out = name.strip()
    for _ in range(3):
        new = _SUFFIXES.sub("", out).strip(" ,.")
        if new == out:
            break
        out = new
    return out
