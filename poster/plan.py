"""upload_plan.csv → Liste der Posts mit festen Terminen."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List

from .config import Config

INSTA = "insta"
TIKTOK = "tiktok"


@dataclass(frozen=True)
class Post:
    id: str          # z. B. "t01_insta_test_1"
    tag: int
    ziel: str        # insta_test_1 … / tiktok_acc1 …
    plattform: str   # insta | tiktok
    video: str       # test_01
    datei: str       # Pfad unter videos/, z. B. "test_01.mp4"
    caption: str
    termin: datetime  # mit Zeitzone


def _uhrzeit(text: str) -> time:
    h, m = text.split(":")
    return time(int(h), int(m))


def zeilen(csv_pfad: Path) -> List[dict]:
    with csv_pfad.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def posts(cfg: Config, start: date = None, csv_pfad: Path = None) -> List[Post]:
    start = start or cfg.start_datum
    if start is None:
        raise RuntimeError("Noch kein Startdatum gesetzt (python -m poster start JJJJ-MM-TT).")
    csv_pfad = csv_pfad or cfg.videos / "upload_plan.csv"
    ergebnis = []
    for z in zeilen(csv_pfad):
        tag = int(z["Tag"])
        ziel = z["Ziel"].strip()
        if ziel.startswith("insta"):
            plattform, uhr = INSTA, cfg.insta_slots[ziel]
        elif ziel.startswith("tiktok"):
            plattform, uhr = TIKTOK, cfg.tiktok_zeit
        else:
            raise ValueError(f"Unbekanntes Ziel in upload_plan.csv: {ziel}")
        termin = datetime.combine(start + timedelta(days=tag - 1), _uhrzeit(uhr), tzinfo=cfg.tz)
        video = z["Video"].strip()
        ergebnis.append(Post(
            id=f"t{tag:02d}_{ziel}", tag=tag, ziel=ziel, plattform=plattform, video=video,
            datei=f"{video}.mp4", caption=z["Caption-Vorschlag"].strip(), termin=termin,
        ))
    ergebnis.sort(key=lambda p: (p.termin, p.ziel))
    return ergebnis
