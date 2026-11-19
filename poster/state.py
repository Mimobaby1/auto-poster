"""state.json: was schon passiert ist. In GitHub Actions wird jede Änderung sofort committet und gepusht,
damit ein abgebrochener Lauf nie zu einem Doppelpost führt."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

OFFEN = "offen"
CONTAINER = "container"          # Insta: Container angelegt, Video wird verarbeitet
VEROEFFENTLICHEN = "veroeffentlichen"  # Insta: Veröffentlichen läuft, Ergebnis noch nicht bestätigt
GEPOSTET = "gepostet"            # Insta: veröffentlicht
EINGEPLANT = "eingeplant"        # TikTok: liegt bei Buffer
FEHLER = "fehler"


class State:
    def __init__(self, pfad: Path, git_sync: bool = None):
        self.pfad = pfad
        self.daten: Dict[str, dict] = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
        self.git_sync = (os.environ.get("POSTER_GIT_SYNC") == "1") if git_sync is None else git_sync

    def get(self, post_id: str) -> dict:
        return self.daten.get(post_id, {"status": OFFEN})

    def status(self, post_id: str) -> str:
        return self.get(post_id).get("status", OFFEN)

    def setzen(self, post_id: str, **werte) -> None:
        eintrag = dict(self.get(post_id))
        eintrag.update(werte)
        eintrag["geaendert"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.daten[post_id] = eintrag
        self.speichern(f"{post_id}: {eintrag.get('status')}")

    def speichern(self, nachricht: str = "state") -> None:
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.daten, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.pfad)
        if self.git_sync:
            _git_push(self.pfad, nachricht)


def _git_push(pfad: Path, nachricht: str) -> None:
    cwd = pfad.parent
    subprocess.run(["git", "add", pfad.name], cwd=cwd, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=cwd).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", f"poster: {nachricht}"], cwd=cwd, check=True)
    for _ in range(3):
        if subprocess.run(["git", "push", "-q"], cwd=cwd).returncode == 0:
            return
        subprocess.run(["git", "pull", "-q", "--rebase"], cwd=cwd)
    raise RuntimeError("state.json konnte nicht gepusht werden – Lauf abgebrochen, damit nichts doppelt gepostet wird.")
