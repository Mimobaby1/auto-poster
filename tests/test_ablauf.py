import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from poster import instagram as ig
from poster import plan as pl
from poster import state as st
from poster.ablauf import Lauf
from poster.buffer import Buffer
from poster.fehler import PosterFehler

BER = ZoneInfo("Europe/Berlin")


class Uhr:
    def __init__(self, zeit):
        self.zeit = zeit

    def __call__(self):
        return self.zeit

    def schlafen(self, sek):
        self.zeit += timedelta(seconds=sek)


class FakeInsta:
    """Simuliert die Instagram-API inkl. Container-Status."""

    def __init__(self, trial_ablehnen=False):
        self.container = {}
        self.erstellt = []
        self.publiziert = []
        self.trial_ablehnen = trial_ablehnen
        self.abbruch_nach_publish = False

    def testreel_container(self, url, caption, strategie):
        if self.trial_ablehnen:
            raise PosterFehler("Instagram: trial_params not supported")
        cid = f"c{len(self.erstellt) + 1}"
        self.erstellt.append({"url": url, "caption": caption, "trial": ig.trial_params(strategie)})
        self.container[cid] = ig.FINISHED
        return cid

    def container_status(self, cid):
        return {"status_code": self.container[cid]}

    def warten_bis_fertig(self, cid):
        return self.container[cid]

    def veroeffentlichen(self, cid):
        self.container[cid] = ig.PUBLISHED
        self.publiziert.append(cid)
        if self.abbruch_nach_publish:
            raise KeyboardInterrupt("Lauf stirbt nach dem Veröffentlichen")
        return "m" + cid


class FakeBuffer:
    def __init__(self):
        self.geplant = {}   # kanal -> list of posts
        self.n = 0

    def posts(self, kanal, status):
        if status == ["scheduled"]:
            return list(self.geplant.get(kanal, []))
        return []

    def einplanen(self, kanal, text, url, termin):
        self.n += 1
        self.geplant.setdefault(kanal, []).append({"id": f"b{self.n}", "text": text, "url": url,
                                                   "dueAt": termin.astimezone(ZoneInfo("UTC")).isoformat()})
        return f"b{self.n}"


def lauf(cfg, tmp_path, uhr, insta=None, buffer=None):
    state = st.State(tmp_path / "state.json", git_sync=False)
    return Lauf(cfg, state, pl.posts(cfg), uhr, insta=insta, buffer=buffer or FakeBuffer(),
                schlafen=uhr.schlafen, log=lambda *_: None), state


def test_jedes_reel_ist_testreel_manual(cfg, tmp_path):
    uhr = Uhr(datetime(2026, 12, 1, 8, 1, tzinfo=BER))
    insta = FakeInsta()
    l, state = lauf(cfg, tmp_path, uhr, insta)
    assert l.ausfuehren() == 0
    assert insta.erstellt == [{"url": "https://x.github.io/repo/videos/test_01.mp4", "caption": "cap eins",
                               "trial": json.dumps({"graduation_strategy": "MANUAL"})}]
    assert state.status("t01_insta_test_1") == st.GEPOSTET
    assert state.status("t01_insta_test_2") == st.OFFEN


def test_ohne_testreel_wird_nie_gepostet(cfg, tmp_path):
    uhr = Uhr(datetime(2026, 12, 1, 8, 1, tzinfo=BER))
    insta = FakeInsta(trial_ablehnen=True)
    l, state = lauf(cfg, tmp_path, uhr, insta)
    assert l.ausfuehren() == 1
    assert insta.publiziert == []
    assert state.get("t01_insta_test_1")["versuche"] == 1


def test_trial_params_nur_gueltige_strategie():
    assert json.loads(ig.trial_params("MANUAL")) == {"graduation_strategy": "MANUAL"}
    with pytest.raises(PosterFehler):
        ig.trial_params("")


def test_container_anfrage_enthaelt_trial_params():
    gesendet = {}

    def handler(req):
        gesendet["body"] = req.content.decode()
        gesendet["auth"] = req.headers["authorization"]
        gesendet["url"] = str(req.url)
        return httpx.Response(200, json={"id": "c1"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        cid = ig.Instagram(http, "GEHEIM", "123").testreel_container("https://v/x.mp4", "hi", "MANUAL")
    assert cid == "c1"
    assert "trial_params=%7B%22graduation_strategy%22%3A+%22MANUAL%22%7D" in gesendet["body"]
    assert "media_type=REELS" in gesendet["body"]
    assert "GEHEIM" not in gesendet["url"] and gesendet["auth"] == "Bearer GEHEIM"


def test_wartet_bis_termin_wenn_lauf_frueh_startet(cfg, tmp_path):
    uhr = Uhr(datetime(2026, 12, 1, 7, 55, tzinfo=BER))
    l, state = lauf(cfg, tmp_path, uhr, FakeInsta())
    l.ausfuehren()
    assert state.status("t01_insta_test_1") == st.GEPOSTET
    assert uhr.zeit >= datetime(2026, 12, 1, 8, 0, tzinfo=BER)


def test_nachholen_mit_abstand(cfg, tmp_path):
    # Morgen- und Mittagslauf ausgefallen: um 13:05 werden beide nachgeholt, 30 min Abstand
    uhr = Uhr(datetime(2026, 12, 1, 13, 5, tzinfo=BER))
    insta = FakeInsta()
    l, state = lauf(cfg, tmp_path, uhr, insta)
    l.ausfuehren()
    assert [e["caption"] for e in insta.erstellt] == ["cap eins", "cap zwei"]
    t1 = datetime.fromisoformat(state.get("t01_insta_test_1")["gepostet_um"])
    t2 = datetime.fromisoformat(state.get("t01_insta_test_2")["gepostet_um"])
    assert t2 - t1 >= timedelta(minutes=30)


def test_kein_doppelpost_nach_abbruch(cfg, tmp_path):
    uhr = Uhr(datetime(2026, 12, 1, 8, 1, tzinfo=BER))
    insta = FakeInsta()
    insta.abbruch_nach_publish = True
    l, state = lauf(cfg, tmp_path, uhr, insta)
    with pytest.raises(KeyboardInterrupt):
        l.ausfuehren()
    assert state.status("t01_insta_test_1") == st.VEROEFFENTLICHEN
    insta.abbruch_nach_publish = False
    l2, state2 = lauf(cfg, tmp_path, uhr, insta)   # neuer Lauf liest state.json neu
    l2.ausfuehren()
    assert len(insta.publiziert) == 1
    assert state2.status("t01_insta_test_1") == st.GEPOSTET


def test_nach_drei_fehlern_aufgeben(cfg, tmp_path):
    uhr = Uhr(datetime(2026, 12, 1, 8, 1, tzinfo=BER))
    insta = FakeInsta(trial_ablehnen=True)
    for _ in range(4):
        l, state = lauf(cfg, tmp_path, uhr, insta)
        l.ausfuehren()
    assert state.status("t01_insta_test_1") == st.FEHLER
    assert state.get("t01_insta_test_1")["versuche"] == 3


def test_buffer_vorrat_max(cfg, tmp_path):
    cfg.buffer_vorrat = 1
    uhr = Uhr(datetime(2026, 11, 30, 12, 0, tzinfo=BER))
    buf = FakeBuffer()
    l, state = lauf(cfg, tmp_path, uhr, FakeInsta(), buf)
    assert l.ausfuehren() == 0
    assert {k: len(v) for k, v in buf.geplant.items()} == {"k1": 1, "k2": 1, "k3": 1}
    assert buf.geplant["k3"][0]["url"].endswith("/videos/test_03.mp4")
    assert state.status("t01_tiktok_acc1") == st.EINGEPLANT
    assert state.status("t02_tiktok_acc1") == st.OFFEN
    # Tag 1 gepostet → Platz frei → Tag 2 wird nachgefüllt
    buf.geplant = {}
    l, state = lauf(cfg, tmp_path, uhr, FakeInsta(), buf)
    l.ausfuehren()
    assert state.status("t02_tiktok_acc1") == st.EINGEPLANT
    assert buf.geplant["k1"][0]["dueAt"].startswith("2026-12-02T17:00")


def test_buffer_kein_duplikat_wenn_schon_da(cfg, tmp_path):
    uhr = Uhr(datetime(2026, 11, 30, 12, 0, tzinfo=BER))
    buf = FakeBuffer()
    termin = datetime(2026, 12, 1, 18, 0, tzinfo=BER)
    buf.geplant["k1"] = [{"id": "alt", "text": "cap eins", "dueAt": "2026-12-01T17:00:00.000Z"}]
    l, state = lauf(cfg, tmp_path, uhr, FakeInsta(), buf)
    l.ausfuehren()
    assert state.get("t01_tiktok_acc1")["buffer_id"] == "alt"
    assert sum(1 for p in buf.geplant["k1"] if p["text"] == "cap eins") == 1
    assert termin


def test_buffer_anfrage_format():
    gesendet = []

    def handler(req):
        body = json.loads(req.content)
        gesendet.append(body)
        if "organizations" in body["query"]:
            return httpx.Response(200, json={"data": {"account": {"organizations": [{"id": "o1", "name": "x"}]}}})
        return httpx.Response(200, json={"data": {"createPost": {"post": {"id": "p1", "dueAt": "x", "status": "scheduled"}}}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        pid = Buffer(http, "KEY").einplanen("k1", "cap", "https://v/x.mp4", datetime(2026, 12, 1, 18, tzinfo=BER))
    assert pid == "p1"
    eingabe = gesendet[-1]["variables"]["input"]
    assert eingabe["dueAt"] == "2026-12-01T17:00:00.000Z"
    assert eingabe["mode"] == "customScheduled" and eingabe["schedulingType"] == "automatic"
    assert eingabe["assets"] == [{"video": {"url": "https://v/x.mp4"}}]


def test_fertig(cfg, tmp_path):
    uhr = Uhr(datetime(2026, 12, 3, 9, 0, tzinfo=BER))
    l, state = lauf(cfg, tmp_path, uhr, FakeInsta())
    l.ausfuehren()
    assert l.fertig()


def test_facebook_token_nutzt_graph_facebook():
    urls = []

    def handler(req):
        urls.append(str(req.url))
        if "assigned_instagram_accounts" in str(req.url):
            return httpx.Response(200, json={"data": [{"id": "1784", "username": "kmas_baby"}]})
        if "debug_token" in str(req.url):
            return httpx.Response(200, json={"data": {"granular_scopes": [
                {"scope": "instagram_content_publish", "target_ids": ["1784"]}]}})
        return httpx.Response(200, json={"id": "c9"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        insta = ig.aus_umgebung(http, "v23.0", "EAAxyz", "")
        assert insta.user_id == "1784"
        insta.testreel_container("https://v/x.mp4", "hi", "MANUAL")
    assert urls[-1].startswith("https://graph.facebook.com/v23.0/1784/media")
    assert all("EAAxyz" not in u.split("input_token=")[0] for u in urls)
