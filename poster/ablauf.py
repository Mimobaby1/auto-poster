"""Ein Lauf (`tick`): fällige Insta-Testreels posten, Buffer-Vorrat für TikTok auffüllen."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Callable, List, Optional

from . import instagram as ig
from . import state as st
from .buffer import Buffer
from .config import Config
from .fehler import PosterFehler
from .plan import INSTA, TIKTOK, Post

VORLAUF = timedelta(minutes=10)     # so früh vor dem Termin darf ein Lauf starten und warten
MAX_VERSUCHE = 3


class Lauf:
    def __init__(self, cfg: Config, state: st.State, posts: List[Post], jetzt: Callable[[], datetime],
                 insta: Optional[ig.Instagram] = None, buffer: Optional[Buffer] = None, trocken: bool = False,
                 schlafen: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print):
        self.cfg, self.state, self.posts = cfg, state, posts
        self.jetzt, self.insta, self.buffer = jetzt, insta, buffer
        self.trocken, self.schlafen, self.log = trocken, schlafen, log
        self.fehler: List[str] = []

    # ---------- Instagram ----------
    def faellige_insta(self) -> List[Post]:
        grenze = self.jetzt() + VORLAUF
        return [p for p in self.posts if p.plattform == INSTA and p.termin <= grenze
                and self.state.status(p.id) not in (st.GEPOSTET, st.FEHLER)]

    def _letzter_insta_post(self) -> Optional[datetime]:
        zeiten = [datetime.fromisoformat(e["gepostet_um"]) for e in self.state.daten.values()
                  if e.get("status") == st.GEPOSTET and e.get("gepostet_um")]
        return max(zeiten) if zeiten else None

    def _warten_bis(self, ziel: datetime, grund: str) -> None:
        rest = (ziel - self.jetzt()).total_seconds()
        if rest > 0:
            self.log(f"  warte {int(rest // 60)} min {int(rest % 60)} s ({grund})")
            if not self.trocken:
                self.schlafen(rest)

    def insta_posten(self) -> None:
        for p in self.faellige_insta():
            self._warten_bis(p.termin, "Termin")
            letzter = self._letzter_insta_post()
            if letzter:
                self._warten_bis(letzter + timedelta(minutes=self.cfg.insta_abstand_min), "Abstand zum letzten Reel")
            if self.trocken:
                self.log(f"[trocken] Insta-Testreel {p.id} ({p.video}) – {p.caption[:50]}")
                continue
            try:
                self._ein_reel(p)
            except PosterFehler as exc:
                versuche = int(self.state.get(p.id).get("versuche", 0)) + 1
                status = st.FEHLER if versuche >= MAX_VERSUCHE else self.state.status(p.id)
                self.state.setzen(p.id, status=status, versuche=versuche, fehler=str(exc))
                self.fehler.append(f"{p.id}: {exc}")
                self.log(f"  FEHLER {p.id} (Versuch {versuche}/{MAX_VERSUCHE}): {exc}")

    def _ein_reel(self, p: Post) -> None:
        if self.insta is None:
            raise PosterFehler("Instagram ist nicht eingerichtet (IG_ACCESS_TOKEN / IG_USER_ID).")
        eintrag = self.state.get(p.id)
        container = eintrag.get("container_id")

        if container:
            code = self.insta.container_status(container).get("status_code", "")
            if code == ig.PUBLISHED:
                self._gepostet(p, container, eintrag.get("media_id", ""))
                return
            if code in (ig.EXPIRED, ig.ERROR):
                container = None

        if not container:
            url = self.cfg.media_url(p.datei)
            container = self.insta.testreel_container(url, p.caption, self.cfg.insta_trial)
            self.state.setzen(p.id, status=st.CONTAINER, container_id=container)
            self.log(f"  {p.id}: Testreel-Container {container} angelegt")

        code = self.insta.warten_bis_fertig(container)
        if code == ig.PUBLISHED:
            self._gepostet(p, container, "")
            return
        if code != ig.FINISHED:
            self.state.setzen(p.id, status=st.OFFEN, container_id=None)
            raise PosterFehler(f"Container {container} ist {code} – wird beim nächsten Lauf neu angelegt.")

        # Erst festhalten (und pushen), dann veröffentlichen: bricht der Lauf hier ab,
        # sieht der nächste Lauf am Container-Status, ob das Reel schon draußen ist.
        self.state.setzen(p.id, status=st.VEROEFFENTLICHEN)
        media_id = self.insta.veroeffentlichen(container)
        self._gepostet(p, container, media_id)

    def _gepostet(self, p: Post, container: str, media_id: str) -> None:
        self.state.setzen(p.id, status=st.GEPOSTET, container_id=container, media_id=media_id,
                          gepostet_um=self.jetzt().isoformat(timespec="seconds"), fehler=None)
        self.log(f"  {p.id}: als Testreel gepostet ({p.video})")

    # ---------- TikTok über Buffer ----------
    def tiktok_auffuellen(self) -> None:
        for ziel, kanal in sorted(self.cfg.tiktok_kanaele.items()):
            offen = [p for p in self.posts if p.plattform == TIKTOK and p.ziel == ziel
                     and self.state.status(p.id) == st.OFFEN]
            if not offen:
                continue
            if self.trocken and (self.buffer is None or not kanal):
                for p in offen[: self.cfg.buffer_vorrat]:
                    self.log(f"[trocken] Buffer {ziel}: {p.id} für {p.termin:%d.%m. %H:%M}")
                continue
            try:
                self._kanal_auffuellen(ziel, kanal, offen)
            except PosterFehler as exc:
                self.fehler.append(f"{ziel}: {exc}")
                self.log(f"  FEHLER Buffer {ziel}: {exc}")

    def _kanal_auffuellen(self, ziel: str, kanal: str, offen: List[Post]) -> None:
        if self.buffer is None:
            raise PosterFehler("Buffer ist nicht eingerichtet (BUFFER_API_KEY).")
        if not kanal:
            raise PosterFehler(f"Buffer-Kanal für {ziel} fehlt in config.json (python -m poster pruefen zeigt die IDs).")
        geplant = self.buffer.posts(kanal, ["scheduled"])
        self._buffer_fehler_melden(ziel, kanal)
        for p in offen:
            if len(geplant) >= self.cfg.buffer_vorrat:
                break
            termin = max(p.termin, self.jetzt() + VORLAUF)
            # Schon da (z. B. Lauf nach dem Einplanen abgebrochen)? Dann übernehmen statt doppelt anlegen.
            vorhanden = next((g for g in geplant if (g.get("text") or "").strip() == p.caption
                              and g.get("dueAt") and abs(datetime.fromisoformat(g["dueAt"].replace("Z", "+00:00"))
                                                         - termin).total_seconds() < 120), None)
            if self.trocken:
                self.log(f"[trocken] Buffer {ziel}: {p.id} für {termin:%d.%m. %H:%M}")
                geplant.append({"id": "trocken"})
                continue
            post_id = vorhanden["id"] if vorhanden else self.buffer.einplanen(kanal, p.caption, self.cfg.media_url(p.datei), termin)
            self.state.setzen(p.id, status=st.EINGEPLANT, buffer_id=post_id, termin=termin.isoformat())
            if not vorhanden:
                geplant.append({"id": post_id})
            self.log(f"  Buffer {ziel}: {p.id} für {termin:%d.%m. %H:%M} eingeplant")

    def _buffer_fehler_melden(self, ziel: str, kanal: str) -> None:
        unsere = {e.get("buffer_id"): pid for pid, e in self.state.daten.items()
                  if e.get("status") == st.EINGEPLANT and e.get("buffer_id")}
        for post in self.buffer.posts(kanal, ["error"]):
            pid = unsere.get(post["id"])
            if pid:
                msg = (post.get("error") or {}).get("message", "unbekannt")
                self.state.setzen(pid, status=st.FEHLER, fehler=f"Buffer: {msg}")
                self.fehler.append(f"{pid}: Buffer konnte nicht posten: {msg}")

    # ---------- gesamt ----------
    def fertig(self) -> bool:
        if not self.posts:
            return False
        ende = max(p.termin for p in self.posts) + timedelta(hours=1)
        offen = [p for p in self.posts if self.state.status(p.id) in (st.OFFEN, st.CONTAINER, st.VEROEFFENTLICHEN)]
        return not offen and self.jetzt() > ende

    def ausfuehren(self) -> int:
        self.log(f"Lauf {self.jetzt():%d.%m.%Y %H:%M} ({self.cfg.zeitzone}){' – TROCKEN' if self.trocken else ''}")
        self.insta_posten()
        self.tiktok_auffuellen()
        if self.fehler:
            self.log("Fehler in diesem Lauf:\n  " + "\n  ".join(self.fehler))
            return 1
        return 0
