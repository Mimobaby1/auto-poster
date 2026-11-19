"""config.json lesen und schreiben, Geheimnisse aus Umgebung oder .env."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    start_datum: Optional[date]
    aktiv: bool
    zeitzone: str
    quelle: str
    media_base_url: str
    insta_slots: Dict[str, str]
    insta_trial: str
    insta_abstand_min: int
    ig_api_version: str
    tiktok_zeit: str
    tiktok_kanaele: Dict[str, str]
    buffer_vorrat: int
    pfad: Path = field(default=ROOT / "config.json", repr=False)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.zeitzone)

    @property
    def root(self) -> Path:
        return self.pfad.parent

    @property
    def videos(self) -> Path:
        return self.root / "videos"

    def quellordner(self) -> Path:
        q = Path(self.quelle)
        return q if q.is_absolute() else (self.root / q).resolve()

    def media_url(self, datei: str) -> str:
        if not self.media_base_url:
            raise RuntimeError("media_base_url fehlt in config.json (öffentliche Adresse der Videos).")
        return self.media_base_url.rstrip("/") + "/videos/" + datei


def laden(pfad: Path = ROOT / "config.json") -> Config:
    data = json.loads(pfad.read_text(encoding="utf-8"))
    start = data.get("start_datum")
    return Config(
        start_datum=date.fromisoformat(start) if start else None,
        aktiv=bool(data.get("aktiv")),
        zeitzone=data.get("zeitzone", "Europe/Berlin"),
        quelle=data["quelle"],
        media_base_url=data.get("media_base_url", ""),
        insta_slots=dict(data["insta_slots"]),
        insta_trial=data.get("insta_trial", "MANUAL"),
        insta_abstand_min=int(data.get("insta_abstand_min", 30)),
        ig_api_version=data.get("ig_api_version", "v23.0"),
        tiktok_zeit=data["tiktok_zeit"],
        tiktok_kanaele=dict(data["tiktok_kanaele"]),
        buffer_vorrat=int(data.get("buffer_vorrat", 10)),
        pfad=pfad,
    )


def speichern(cfg: Config) -> None:
    data = json.loads(cfg.pfad.read_text(encoding="utf-8"))
    data["start_datum"] = cfg.start_datum.isoformat() if cfg.start_datum else None
    data["aktiv"] = cfg.aktiv
    data["media_base_url"] = cfg.media_base_url
    data["tiktok_kanaele"] = cfg.tiktok_kanaele
    cfg.pfad.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def geheimnis(name: str, root: Path = ROOT) -> str:
    """Erst Umgebungsvariable (GitHub-Secret), dann .env im Projektordner."""
    wert = os.environ.get(name, "").strip()
    if wert:
        return wert
    env = root / ".env"
    if env.exists():
        for zeile in env.read_text(encoding="utf-8").splitlines():
            if "=" in zeile and not zeile.lstrip().startswith("#"):
                k, v = zeile.split("=", 1)
                if k.strip() == name:
                    return v.strip().strip('"').strip("'")
    return ""
