"""Cliente de la API de Claude (Anthropic) con búsqueda web, sin dependencias externas."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

ENDPOINT = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"


class ClaudeError(Exception):
    pass


def _post(api_key: str, body: dict) -> dict:
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        raise ClaudeError(f"Error {e.code} de la API de Claude. {detail}".strip()) from e


def ask(api_key: str, system: str, user_text: str, model: str = DEFAULT_MODEL,
        max_searches: int = 8, max_tokens: int = 16000, max_continuations: int = 5) -> dict:
    """Devuelve {"text": str, "sources": [{"title", "url"}]}."""
    if not api_key:
        raise ClaudeError("Falta la clave de API de Anthropic.")
    messages = [{"role": "user", "content": user_text}]
    text_parts, sources = [], {}
    for _ in range(max_continuations):
        body = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
        if max_searches > 0:
            body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
        resp = _post(api_key, body)
        content = resp.get("content") or []
        for block in content:
            if block.get("type") != "text":
                continue
            text_parts.append(block.get("text", ""))
            for c in block.get("citations") or []:
                url = c.get("url") or ""
                if url.startswith("http") and url not in sources:
                    sources[url] = {"title": c.get("title") or url, "url": url}
        stop = resp.get("stop_reason")
        if stop == "pause_turn":
            # La API pausó una búsqueda larga: se reenvía el turno tal cual para que continúe.
            messages.append({"role": "assistant", "content": content})
            continue
        if stop == "refusal":
            raise ClaudeError("La IA no pudo completar este pedido.")
        break
    return {"text": "".join(text_parts).strip(), "sources": list(sources.values())}
