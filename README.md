# Auto-Poster

Postet die Test-Kampagne aus dem Kmas-Cutter (`3_test`, 21 Tage) von allein:

| Wo | Was | Wann |
|---|---|---|
| Main-Insta | 3 **Testreels** pro Tag (nur Nicht-Follower sehen sie; Freigabe an Follower nur, wenn du sie in der App antippst) | 08:00, 13:00, 19:00 |
| TikTok-Account 1–3 | je 1 Video pro Tag, über Buffer | 18:00 |

Läuft in der Cloud über GitHub Actions. Dein Mac muss nach dem Start nicht an sein. Die Posts kommen etwa 5–20 Minuten nach der Wunschzeit, weil GitHub nicht minutengenau startet.

Einrichtung: [EINRICHTUNG.md](EINRICHTUNG.md)

## Befehle (im Ordner `Auto-Poster`)

```
.venv/bin/python -m poster einlesen            # Videos + upload_plan.csv aus dem Kmas-Ordner übernehmen
.venv/bin/python -m poster plan --start 2026-12-01   # alle Termine ansehen (Probe-Datum)
.venv/bin/python -m poster pruefen             # alles grün? (Videos, Adresse, Instagram, Buffer)
.venv/bin/python -m poster test-insta          # Testreel-Container anlegen, NICHT posten
.venv/bin/python -m poster test-buffer tiktok_acc1   # TikTok-Post einplanen und sofort löschen
.venv/bin/python -m poster start 2026-12-01    # Startdatum setzen, Kampagne aktiv
.venv/bin/python -m poster status              # Stand
.venv/bin/python -m poster stop                # pausieren
.venv/bin/python -m poster tick --trocken --jetzt 2026-12-01T08:00   # Lauf simulieren
.venv/bin/python -m pytest -q                  # Tests
```

## Aufbau

```
config.json        Startdatum, Uhrzeiten, Testreel-Modus (MANUAL), Buffer-Kanäle, öffentliche Video-Adresse
videos/            jedes Video einmal (test_01.mp4 …) + upload_plan.csv mit den Captions
state.json         was schon gepostet/eingeplant ist (GitHub committet das nach jedem Schritt)
poster/plan.py     Termine aus upload_plan.csv
poster/instagram.py  Testreel-Container (immer mit trial_params) → verarbeiten → veröffentlichen
poster/buffer.py   TikTok-Posts bei Buffer einplanen (Vorrat max. 10 pro Account, wird laufend nachgefüllt)
poster/ablauf.py   ein Lauf: fällige Reels posten (verpasste nachholen, 30 min Abstand), Buffer auffüllen
.github/workflows/poster.yml   startet die Läufe; schaltet sich nach Tag 21 selbst ab
```

## Sicherheitsnetze

- Ein Reel ohne Testreel-Markierung wird nie gepostet. Lehnt Instagram sie ab, bricht der Post ab und der Lauf wird rot.
- Kein Doppelpost: Der Stand wird vor dem Veröffentlichen gespeichert und gepusht, und ein neuer Lauf prüft zuerst den Container-Status bei Instagram.
- Ein Fehler macht den Lauf rot, und GitHub schickt dir eine E-Mail. Nach 3 Fehlversuchen wird ein Post übersprungen; `status` zeigt ihn an.
