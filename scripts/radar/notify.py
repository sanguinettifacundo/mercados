"""Avisos al celular por ntfy (app gratuita) y, opcionalmente, por Telegram."""
from __future__ import annotations

import json
import os
import urllib.request


def _post_json(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def channels() -> dict:
    return {
        "ntfy": bool(os.environ.get("NTFY_TOPIC")),
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")),
    }


def send(title: str, message: str, click_url: str = "", tags=None, priority: int = 3) -> list:
    """Envía el aviso por los canales configurados. Devuelve la lista de errores (vacía si salió bien)."""
    errors = []
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic:
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
        payload = {"topic": topic, "title": title, "message": message, "priority": priority}
        if tags:
            payload["tags"] = tags
        if click_url:
            payload["click"] = click_url
        try:
            _post_json(server, payload)
        except Exception as e:  # noqa: BLE001
            errors.append(f"ntfy: {e}")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        text = f"{title}\n\n{message}" + (f"\n\n{click_url}" if click_url else "")
        try:
            _post_json(f"https://api.telegram.org/bot{token}/sendMessage",
                       {"chat_id": chat, "text": text, "disable_web_page_preview": True})
        except Exception as e:  # noqa: BLE001
            errors.append(f"telegram: {e}")
    return errors
