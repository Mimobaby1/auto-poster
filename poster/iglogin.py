"""Plan B: Instagram-Token über einen direkten Login-Link holen (Business Login for Instagram)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .fehler import PosterFehler

AUTHORIZE = "https://www.instagram.com/oauth/authorize"
TOKEN = "https://api.instagram.com/oauth/access_token"
LONG = "https://graph.instagram.com/access_token"
SCOPES = "instagram_business_basic,instagram_business_content_publish"


def redirect_uri(media_base_url: str) -> str:
    return media_base_url.rstrip("/") + "/callback.html"


def login_link(app_id: str, redirect: str) -> str:
    return AUTHORIZE + "?" + urlencode({
        "force_reauth": "true", "client_id": app_id, "redirect_uri": redirect,
        "response_type": "code", "scope": SCOPES,
    })


def _json(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError as exc:
        raise PosterFehler(f"Instagram-Antwort unlesbar (HTTP {resp.status_code})") from exc
    if resp.status_code >= 400 or "error" in data or "error_message" in data:
        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        raise PosterFehler("Instagram: " + str(err.get("message") or data.get("error_message") or data))
    return data


def code_tauschen(http: httpx.Client, app_id: str, secret: str, redirect: str, code: str) -> tuple:
    """Code → kurzlebiger Token → 60-Tage-Token. Gibt (token, user_id, gültig_sekunden) zurück."""
    code = code.strip().removesuffix("#_") if hasattr(str, "removesuffix") else code.strip().rstrip("#_")
    kurz = _json(http.post(TOKEN, data={"client_id": app_id, "client_secret": secret, "grant_type": "authorization_code",
                                        "redirect_uri": redirect, "code": code}, timeout=30))
    if isinstance(kurz.get("data"), list):
        kurz = kurz["data"][0]
    lang = _json(http.get(LONG, params={"grant_type": "ig_exchange_token", "client_secret": secret,
                                        "access_token": kurz["access_token"]}, timeout=30))
    return lang["access_token"], str(kurz.get("user_id", "")), int(lang.get("expires_in", 0))


def env_setzen(env: Path, werte: dict) -> None:
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    for name, wert in werte.items():
        zeile = f"{name}={wert}"
        if re.search(rf"^{name}=.*$", text, flags=re.M):
            text = re.sub(rf"^{name}=.*$", lambda _m: zeile, text, flags=re.M)
        else:
            text += ("" if text.endswith("\n") else "\n") + zeile + "\n"
    env.write_text(text, encoding="utf-8")
