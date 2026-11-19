"""Buffer-API (GraphQL, https://api.buffer.com): TikTok-Posts für einen festen Termin einplanen.

Buffer lädt das Video erst zum Posten von der öffentlichen URL. Der Key steht nur im Header.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from .fehler import PosterFehler

ENDPOINT = "https://api.buffer.com"

Q_ORGS = "query { account { organizations { id name } } }"
Q_KANAELE = """query Kanaele($org: OrganizationId!) {
  channels(input: {organizationId: $org}) { id name displayName service isQueuePaused isDisconnected }
}"""
Q_POSTS = """query Posts($org: OrganizationId!, $kanal: ChannelId!, $status: [PostStatus!], $after: String) {
  posts(first: 50, after: $after, input: {organizationId: $org, filter: {channelIds: [$kanal], status: $status},
        sort: [{field: dueAt, direction: asc}]}) {
    edges { node { id dueAt status text error { message } } }
    pageInfo { hasNextPage endCursor }
  }
}"""
M_POST = """mutation Einplanen($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt status } }
    ... on MutationError { message }
  }
}"""
M_LOESCHEN = """mutation Loeschen($input: DeletePostInput!) {
  deletePost(input: $input) {
    ... on DeletePostSuccess { id }
    ... on MutationError { message }
  }
}"""


def iso_utc(zeit: datetime) -> str:
    return zeit.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Buffer:
    def __init__(self, http: httpx.Client, key: str):
        if not key:
            raise PosterFehler("BUFFER_API_KEY fehlt.")
        self.http = http
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self._org: Optional[str] = None

    def _frage(self, query: str, variablen: dict = None) -> dict:
        resp = self.http.post(ENDPOINT, headers=self.headers, timeout=60,
                              content=json.dumps({"query": query, "variables": variablen or {}}))
        if resp.status_code == 401:
            raise PosterFehler("Buffer: API-Key ungültig (401).")
        if resp.status_code == 429:
            raise PosterFehler(f"Buffer: Anfragelimit erreicht, wieder ab {resp.headers.get('Retry-After', '?')} s.")
        try:
            data = resp.json()
        except ValueError as exc:
            raise PosterFehler(f"Buffer-Antwort unlesbar (HTTP {resp.status_code})") from exc
        if data.get("errors"):
            raise PosterFehler("Buffer: " + "; ".join(e.get("message", "?") for e in data["errors"]))
        return data.get("data") or {}

    def organisation(self) -> str:
        if self._org is None:
            orgs = self._frage(Q_ORGS)["account"]["organizations"]
            if not orgs:
                raise PosterFehler("Buffer: keine Organisation im Konto gefunden.")
            self._org = orgs[0]["id"]
        return self._org

    def kanaele(self) -> List[dict]:
        return self._frage(Q_KANAELE, {"org": self.organisation()})["channels"]

    def posts(self, kanal_id: str, status: List[str]) -> List[dict]:
        ergebnis, after = [], None
        while True:
            data = self._frage(Q_POSTS, {"org": self.organisation(), "kanal": kanal_id, "status": status,
                                         "after": after})["posts"]
            ergebnis += [e["node"] for e in data["edges"]]
            if not data["pageInfo"]["hasNextPage"]:
                return ergebnis
            after = data["pageInfo"]["endCursor"]

    def einplanen(self, kanal_id: str, text: str, video_url: str, termin: datetime) -> str:
        eingabe = {
            "channelId": kanal_id,
            "text": text,
            "schedulingType": "automatic",
            "mode": "customScheduled",
            "dueAt": iso_utc(termin),
            "needsApproval": False,
            "assets": [{"video": {"url": video_url}}],
            "metadata": {"tiktok": {"isAiGenerated": False}},
        }
        data = self._frage(M_POST, {"input": eingabe})["createPost"]
        if "post" not in data:
            raise PosterFehler(f"Buffer hat den Post abgelehnt: {data.get('message', data)}")
        return data["post"]["id"]

    def loeschen(self, post_id: str) -> None:
        data = self._frage(M_LOESCHEN, {"input": {"id": post_id}})["deletePost"]
        if "id" not in data:
            raise PosterFehler(f"Buffer: Löschen fehlgeschlagen: {data.get('message', data)}")
