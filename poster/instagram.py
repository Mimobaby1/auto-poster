"""Instagram-API (Instagram Login): Reels ausschließlich als Testreels veröffentlichen.

Ablauf laut Meta: Container mit media_type=REELS, video_url und trial_params anlegen → warten,
bis status_code FINISHED ist → media_publish. Der Token steht nur im Authorization-Header,
nie in einer URL, damit er in keinem Log landet.
"""

from __future__ import annotations

import json
import time
from typing import Callable, Optional

import httpx

from .fehler import PosterFehler

GRAPH_HOST = "https://graph.instagram.com"      # Token aus dem Instagram-Login (beginnt mit IG…)
FACEBOOK_HOST = "https://graph.facebook.com"    # Token aus Facebook/Business-Portfolio (beginnt mit EAA…)


def host_fuer(token: str) -> str:
    return FACEBOOK_HOST if token.startswith("EAA") else GRAPH_HOST
GRADUATION = ("MANUAL", "SS_PERFORMANCE")

# status_code eines Containers
FINISHED = "FINISHED"
IN_PROGRESS = "IN_PROGRESS"
PUBLISHED = "PUBLISHED"
EXPIRED = "EXPIRED"
ERROR = "ERROR"


def _antwort(resp: httpx.Response) -> dict:
    try:
        data = resp.json()
    except ValueError as exc:
        raise PosterFehler(f"Instagram-Antwort unlesbar (HTTP {resp.status_code})") from exc
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error") or {}
        teile = [str(err.get("code", resp.status_code)), err.get("error_user_msg") or err.get("message", "")]
        raise PosterFehler("Instagram: " + " – ".join(t for t in teile if t))
    return data


def trial_params(strategie: str) -> str:
    if strategie not in GRADUATION:
        raise PosterFehler(f"insta_trial muss MANUAL oder SS_PERFORMANCE sein, nicht {strategie!r}.")
    return json.dumps({"graduation_strategy": strategie})


class Instagram:
    def __init__(self, http: httpx.Client, token: str, user_id: str, version: str = "v23.0",
                 host: str = None, schlafen: Callable[[float], None] = time.sleep):
        if not token or not user_id:
            raise PosterFehler("IG_ACCESS_TOKEN oder IG_USER_ID fehlt.")
        self.http = http
        self.user_id = user_id
        self.host = host or host_fuer(token)
        self.basis = f"{self.host}/{version}"
        self.headers = {"Authorization": f"Bearer {token}"}
        self.schlafen = schlafen

    def ich(self) -> dict:
        if self.host == FACEBOOK_HOST:
            return _antwort(self.http.get(f"{self.basis}/{self.user_id}", params={"fields": "id,username"},
                                          headers=self.headers, timeout=30))
        return _antwort(self.http.get(f"{self.basis}/me", params={"fields": "user_id,username,account_type"},
                                      headers=self.headers, timeout=30))

    def testreel_container(self, video_url: str, caption: str, strategie: str) -> str:
        """Legt einen Reel-Container an, IMMER mit trial_params. Ohne Testreel-Markierung gibt es keinen Container."""
        daten = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "trial_params": trial_params(strategie),
        }
        data = _antwort(self.http.post(f"{self.basis}/{self.user_id}/media", data=daten,
                                       headers=self.headers, timeout=60))
        if not data.get("id"):
            raise PosterFehler("Instagram hat keine Container-ID geliefert.")
        return data["id"]

    def container_status(self, container_id: str) -> dict:
        return _antwort(self.http.get(f"{self.basis}/{container_id}", params={"fields": "status_code,status"},
                                      headers=self.headers, timeout=30))

    def warten_bis_fertig(self, container_id: str, max_sekunden: int = 900, intervall: int = 10) -> str:
        """Gibt den End-Status zurück (FINISHED, PUBLISHED, ERROR, EXPIRED)."""
        gewartet = 0
        while True:
            info = self.container_status(container_id)
            code = info.get("status_code", "")
            if code != IN_PROGRESS:
                if code == ERROR:
                    raise PosterFehler(f"Instagram konnte das Video nicht verarbeiten: {info.get('status', '')}")
                return code
            if gewartet >= max_sekunden:
                raise PosterFehler("Instagram verarbeitet das Video seit über 15 Minuten – nächster Lauf versucht es weiter.")
            self.schlafen(intervall)
            gewartet += intervall

    def veroeffentlichen(self, container_id: str) -> str:
        data = _antwort(self.http.post(f"{self.basis}/{self.user_id}/media_publish",
                                       data={"creation_id": container_id}, headers=self.headers, timeout=60))
        return data.get("id", "")


def http_client() -> httpx.Client:
    return httpx.Client(follow_redirects=True)


def konto_id_ermitteln(http: httpx.Client, token: str, version: str = "v23.0") -> str:
    """Findet die Instagram-Konto-ID zum Token, falls IG_USER_ID leer ist."""
    auth = {"Authorization": f"Bearer {token}"}
    if host_fuer(token) == GRAPH_HOST:
        return str(_antwort(http.get(f"{GRAPH_HOST}/{version}/me", params={"fields": "user_id"},
                                     headers=auth, timeout=30)).get("user_id", ""))
    daten = _antwort(http.get(f"{FACEBOOK_HOST}/{version}/debug_token", params={"input_token": token},
                              headers=auth, timeout=30)).get("data", {})
    for g in daten.get("granular_scopes", []):
        if g.get("scope") == "instagram_content_publish" and g.get("target_ids"):
            if len(g["target_ids"]) > 1:
                raise PosterFehler("Der Token sieht mehrere Instagram-Konten – IG_USER_ID bitte festlegen.")
            return str(g["target_ids"][0])
    # Über die Facebook-Seite, mit der das Insta verknüpft ist
    seiten = _antwort(http.get(f"{FACEBOOK_HOST}/{version}/me/accounts",
                               params={"fields": "name,instagram_business_account"},
                               headers=auth, timeout=30)).get("data", [])
    konten = [s["instagram_business_account"]["id"] for s in seiten if s.get("instagram_business_account")]
    if len(konten) == 1:
        return str(konten[0])
    if len(konten) > 1:
        raise PosterFehler("Der Token sieht mehrere Instagram-Konten – IG_USER_ID bitte festlegen.")
    raise PosterFehler("Der Token sieht noch kein Instagram-Konto (im Business-Portfolio dem Systemnutzer zuweisen).")


def aus_umgebung(http: httpx.Client, version: str, token: str, user_id: str) -> Optional[Instagram]:
    if not token:
        return None
    return Instagram(http, token, user_id or konto_id_ermitteln(http, token, version), version)
