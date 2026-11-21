"""Befehle: einlesen | plan | pruefen | start | stop | status | tick | test-insta | test-buffer"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config as konf
from . import instagram as ig
from . import plan as pl
from . import state as st
from .ablauf import Lauf
from .buffer import Buffer
from .fehler import PosterFehler

WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _hash(pfad: Path) -> str:
    h = hashlib.sha256()
    with pfad.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def einlesen(cfg: konf.Config, args) -> int:
    """Kopiert jedes Video aus dem Kmas-Ordner genau einmal nach videos/<Video>.mp4."""
    quelle = Path(args.quelle).expanduser().resolve() if args.quelle else cfg.quellordner()
    csv_pfad = quelle / "upload_plan.csv"
    if not csv_pfad.exists():
        print(f"upload_plan.csv nicht gefunden in {quelle}")
        return 1
    gruppen = defaultdict(list)
    for z in pl.zeilen(csv_pfad):
        gruppen[z["Video"].strip()].append(quelle / z["Datei"].strip())
    cfg.videos.mkdir(exist_ok=True)
    for video, dateien in sorted(gruppen.items()):
        fehlend = [d for d in dateien if not d.exists()]
        if fehlend:
            print(f"Fehlt: {', '.join(str(d) for d in fehlend)}")
            return 1
        hashes = {_hash(d) for d in dateien}
        if len(hashes) != 1:
            print(f"{video}: Insta- und TikTok-Datei sind verschieden – erwartet waren identische Videos.")
            return 1
        ziel = cfg.videos / f"{video}.mp4"
        if not ziel.exists() or _hash(ziel) not in hashes:
            shutil.copy2(dateien[0], ziel)
    shutil.copy2(csv_pfad, cfg.videos / "upload_plan.csv")
    groesse = sum(f.stat().st_size for f in cfg.videos.glob("*.mp4")) / 1e6
    print(f"{len(gruppen)} Videos in {cfg.videos} ({groesse:.0f} MB), upload_plan.csv übernommen.")
    return 0


def plan_zeigen(cfg: konf.Config, args) -> int:
    start = date.fromisoformat(args.start) if args.start else cfg.start_datum
    state = st.State(cfg.root / "state.json", git_sync=False)
    posts = pl.posts(cfg, start)
    tag = None
    for p in posts:
        if p.tag != tag:
            tag = p.tag
            print(f"\nTag {p.tag:2d} – {WOCHENTAG[p.termin.weekday()]} {p.termin:%d.%m.%Y}")
        print(f"  {p.termin:%H:%M}  {p.ziel:<13} {p.video}  [{state.status(p.id)}]  {p.caption[:60]}")
    n_i = sum(p.plattform == pl.INSTA for p in posts)
    print(f"\n{n_i} Insta-Testreels, {len(posts) - n_i} TikToks.")
    return 0


def _http():
    return ig.http_client()


def _insta(cfg, http):
    return ig.aus_umgebung(http, cfg.ig_api_version, konf.geheimnis("IG_ACCESS_TOKEN", cfg.root),
                           konf.geheimnis("IG_USER_ID", cfg.root))


def _buffer(cfg, http):
    key = konf.geheimnis("BUFFER_API_KEY", cfg.root)
    return Buffer(http, key) if key else None


def pruefen(cfg: konf.Config, args) -> int:
    ok = True

    def zeile(gut: bool, text: str):
        nonlocal ok
        ok &= gut
        print(("  ✔ " if gut else "  ✘ ") + text)

    print("Dateien")
    csv_pfad = cfg.videos / "upload_plan.csv"
    zeile(csv_pfad.exists(), "videos/upload_plan.csv")
    if csv_pfad.exists():
        posts = pl.posts(cfg, cfg.start_datum or date.today())
        fehlend = sorted({p.datei for p in posts if not (cfg.videos / p.datei).exists()})
        zeile(not fehlend, f"{len({p.datei for p in posts})} Videos vorhanden" + (f", fehlen: {fehlend[:3]}" if fehlend else ""))
    zeile(bool(cfg.start_datum), f"Startdatum: {cfg.start_datum or 'noch keins'}")
    zeile(cfg.insta_trial == "MANUAL", f"Insta nur als Testreel, Freigabe an Follower: {cfg.insta_trial}")

    with _http() as http:
        print("Öffentliche Video-Adresse")
        if cfg.media_base_url:
            url = cfg.media_url("test_01.mp4")
            try:
                r = http.head(url, timeout=30)
                zeile(r.status_code == 200 and "video" in r.headers.get("content-type", ""),
                      f"{url} → HTTP {r.status_code}, {r.headers.get('content-type', '?')}")
            except Exception as exc:  # noqa: BLE001
                zeile(False, f"{url} nicht erreichbar: {exc.__class__.__name__}")
        else:
            zeile(False, "media_base_url ist noch leer")

        print("Instagram")
        try:
            insta = _insta(cfg, http)
            if insta is None:
                zeile(False, "IG_ACCESS_TOKEN / IG_USER_ID fehlen")
            else:
                me = insta.ich()
                zeile(True, f"verbunden als @{me.get('username')} ({me.get('account_type')})")
        except PosterFehler as exc:
            zeile(False, str(exc))

        print("Buffer / TikTok")
        try:
            buf = _buffer(cfg, http)
            if buf is None:
                zeile(False, "BUFFER_API_KEY fehlt")
            else:
                kanaele = buf.kanaele()
                for k in kanaele:
                    print(f"     Kanal {k['id']}  {k.get('service')}  {k.get('displayName') or k.get('name')}"
                          + ("  (getrennt!)" if k.get("isDisconnected") else "")
                          + ("  (Warteschlange pausiert!)" if k.get("isQueuePaused") else ""))
                ids = {k["id"]: k for k in kanaele}
                for ziel, kid in sorted(cfg.tiktok_kanaele.items()):
                    k = ids.get(kid)
                    zeile(bool(k) and "tiktok" in str(k.get("service", "")).lower() and not k.get("isDisconnected")
                          and not k.get("isQueuePaused"),
                          f"{ziel} → {kid or '(leer)'} {('= ' + (k.get('displayName') or k.get('name'))) if k else ''}")
        except PosterFehler as exc:
            zeile(False, str(exc))

    print("\nAlles bereit." if ok else "\nNoch nicht alles bereit (✘ oben).")
    return 0 if ok else 1


def start(cfg: konf.Config, args) -> int:
    cfg.start_datum = date.fromisoformat(args.datum)
    cfg.aktiv = True
    konf.speichern(cfg)
    posts = pl.posts(cfg)
    print(f"Start: {cfg.start_datum:%d.%m.%Y}. Erstes Reel {posts[0].termin:%d.%m. %H:%M}, "
          f"letzter Post {posts[-1].termin:%d.%m.%Y %H:%M}. Kampagne ist aktiv.")
    return 0


def stop(cfg: konf.Config, args) -> int:
    cfg.aktiv = False
    konf.speichern(cfg)
    print("Kampagne pausiert. Schon bei Buffer eingeplante TikToks laufen weiter – die löschst du in Buffer.")
    return 0


def status(cfg: konf.Config, args) -> int:
    state = st.State(cfg.root / "state.json", git_sync=False)
    if not cfg.start_datum:
        print("Noch kein Startdatum.")
        return 0
    posts = pl.posts(cfg)
    zaehler = defaultdict(int)
    for p in posts:
        zaehler[(p.plattform, state.status(p.id))] += 1
    print(f"Aktiv: {'ja' if cfg.aktiv else 'nein'}, Start {cfg.start_datum:%d.%m.%Y}")
    for (plattform, s), n in sorted(zaehler.items()):
        print(f"  {plattform:<7} {s:<16} {n}")
    for p in posts:
        e = state.get(p.id)
        if e.get("status") == st.FEHLER or e.get("fehler"):
            print(f"  ! {p.id}: {e.get('fehler')}")
    return 0


def tick(cfg: konf.Config, args) -> int:
    if not cfg.aktiv or not cfg.start_datum:
        print("Kampagne nicht aktiv – nichts zu tun.")
        return 0
    jetzt_fest = datetime.fromisoformat(args.jetzt).replace(tzinfo=cfg.tz) if args.jetzt else None
    versatz = (jetzt_fest - datetime.now(cfg.tz)) if jetzt_fest else timedelta(0)

    def jetzt():
        return datetime.now(cfg.tz) + versatz

    state = st.State(cfg.root / "state.json", git_sync=False if args.trocken else None)
    with _http() as http:
        insta = None if args.trocken else _insta(cfg, http)
        buf = None if args.trocken else _buffer(cfg, http)
        lauf = Lauf(cfg, state, pl.posts(cfg), jetzt, insta=insta, buffer=buf, trocken=args.trocken)
        code = lauf.ausfuehren()
        if lauf.fertig():
            print("KAMPAGNE FERTIG")
            ausgabe = os.environ.get("GITHUB_OUTPUT")
            if ausgabe:
                with open(ausgabe, "a", encoding="utf-8") as f:
                    f.write("fertig=true\n")
    return code


def test_insta(cfg: konf.Config, args) -> int:
    """Machbarkeitstest: Testreel-Container anlegen und verarbeiten lassen, NICHT veröffentlichen."""
    with _http() as http:
        insta = _insta(cfg, http)
        if insta is None:
            print("IG_ACCESS_TOKEN / IG_USER_ID fehlen.")
            return 1
        url = cfg.media_url(args.datei)
        print(f"Lege Testreel-Container für {url} an (wird nicht veröffentlicht) …")
        container = insta.testreel_container(url, "test – wird nicht gepostet", cfg.insta_trial)
        code = insta.warten_bis_fertig(container)
        print(f"Container {container}: {code}. Nicht veröffentlicht; er verfällt nach 24 h von selbst.")
        return 0 if code == ig.FINISHED else 1


def test_buffer(cfg: konf.Config, args) -> int:
    """Machbarkeitstest: Post 60 Tage in der Zukunft einplanen und sofort wieder löschen."""
    kanal = cfg.tiktok_kanaele.get(args.ziel) or args.ziel
    with _http() as http:
        buf = _buffer(cfg, http)
        if buf is None:
            print("BUFFER_API_KEY fehlt.")
            return 1
        termin = datetime.now(cfg.tz) + timedelta(days=60)
        post_id = buf.einplanen(kanal, "test – wird sofort gelöscht", cfg.media_url(args.datei), termin)
        print(f"Eingeplant als {post_id} für {termin:%d.%m.%Y} – lösche wieder …")
        buf.loeschen(post_id)
        print("Gelöscht. Buffer nimmt Videos über die öffentliche Adresse an.")
        return 0


def ig_link(cfg: konf.Config, args) -> int:
    from . import iglogin
    app_id = konf.geheimnis("IG_APP_ID", cfg.root)
    if not app_id:
        print("IG_APP_ID fehlt in der .env (Instagram-App-ID von der Meta-Seite).")
        return 1
    print(iglogin.login_link(app_id, iglogin.redirect_uri(cfg.media_base_url)))
    return 0


def ig_token(cfg: konf.Config, args) -> int:
    from . import iglogin
    werte = {n: konf.geheimnis(n, cfg.root) for n in ("IG_APP_ID", "IG_APP_SECRET", "IG_CODE")}
    fehlt = [n for n, v in werte.items() if not v]
    if fehlt:
        print("Fehlt in der .env: " + ", ".join(fehlt))
        return 1
    with _http() as http:
        token, user_id, sekunden = iglogin.code_tauschen(http, werte["IG_APP_ID"], werte["IG_APP_SECRET"],
                                                         iglogin.redirect_uri(cfg.media_base_url), werte["IG_CODE"])
        name = ig.Instagram(http, token, user_id, cfg.ig_api_version).ich().get("username")
    iglogin.env_setzen(cfg.root / ".env", {"IG_ACCESS_TOKEN": token, "IG_USER_ID": user_id, "IG_CODE": ""})
    print(f"Token für @{name} gespeichert, gültig {sekunden // 86400} Tage.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poster")
    sub = parser.add_subparsers(dest="befehl", required=True)
    p = sub.add_parser("einlesen", help="Videos aus dem Kmas-Ordner übernehmen")
    p.add_argument("--quelle")
    p = sub.add_parser("plan", help="alle Termine zeigen")
    p.add_argument("--start", help="Probe-Startdatum JJJJ-MM-TT")
    sub.add_parser("pruefen", help="Dateien, Adresse, Instagram und Buffer prüfen")
    p = sub.add_parser("start", help="Startdatum setzen und Kampagne aktivieren")
    p.add_argument("datum")
    sub.add_parser("stop", help="Kampagne pausieren")
    sub.add_parser("status", help="Stand anzeigen")
    p = sub.add_parser("tick", help="ein Lauf (macht GitHub automatisch)")
    p.add_argument("--trocken", action="store_true", help="nur anzeigen, nichts posten")
    p.add_argument("--jetzt", help="Uhr vorstellen, z. B. 2026-12-01T08:00 (nur mit --trocken sinnvoll)")
    p = sub.add_parser("test-insta", help="Machbarkeitstest Instagram (postet nichts)")
    p.add_argument("--datei", default="test_01.mp4")
    p = sub.add_parser("test-buffer", help="Machbarkeitstest Buffer (plant ein und löscht sofort)")
    p.add_argument("ziel", help="tiktok_acc1 oder eine Kanal-ID")
    p.add_argument("--datei", default="test_01.mp4")
    sub.add_parser("ig-link", help="Plan B: Login-Link für Instagram ausgeben")
    sub.add_parser("ig-token", help="Plan B: Code aus der .env gegen einen 60-Tage-Token tauschen")
    args = parser.parse_args(argv)

    cfg = konf.laden()
    befehle = {"einlesen": einlesen, "plan": plan_zeigen, "pruefen": pruefen, "start": start, "stop": stop,
               "status": status, "tick": tick, "ig-link": ig_link, "ig-token": ig_token, "test-insta": test_insta, "test-buffer": test_buffer}
    try:
        return befehle[args.befehl](cfg, args)
    except PosterFehler as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
