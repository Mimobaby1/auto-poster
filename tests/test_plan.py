from datetime import date, datetime
from zoneinfo import ZoneInfo

from poster import plan as pl

BER = ZoneInfo("Europe/Berlin")


def test_termine_und_zuordnung(cfg):
    posts = pl.posts(cfg)
    assert len(posts) == 12
    p = {x.id: x for x in posts}
    assert p["t01_insta_test_1"].termin == datetime(2026, 12, 1, 8, 0, tzinfo=BER)
    assert p["t01_insta_test_2"].termin == datetime(2026, 12, 1, 13, 0, tzinfo=BER)
    assert p["t01_insta_test_3"].termin == datetime(2026, 12, 1, 19, 0, tzinfo=BER)
    assert p["t02_tiktok_acc3"].termin == datetime(2026, 12, 2, 18, 0, tzinfo=BER)
    assert p["t02_tiktok_acc3"].datei == "test_06.mp4"
    assert p["t01_tiktok_acc1"].video == p["t01_insta_test_1"].video == "test_01"
    assert p["t02_insta_test_2"].caption == "cap fünf"


def test_sommerzeit_utc(cfg):
    posts = pl.posts(cfg, start=date(2027, 7, 1))
    reel = next(x for x in posts if x.id == "t01_insta_test_1")
    assert reel.termin.utcoffset().total_seconds() == 2 * 3600   # 08:00 Berlin = 06:00 UTC
    posts = pl.posts(cfg, start=date(2026, 12, 1))
    reel = next(x for x in posts if x.id == "t01_insta_test_1")
    assert reel.termin.utcoffset().total_seconds() == 3600       # 08:00 Berlin = 07:00 UTC


def test_workflow_cron_deckt_alle_slots():
    """Jeder Insta-Slot muss im Winter und im Sommer von einem Cron-Lauf (UTC) abgedeckt sein."""
    from pathlib import Path
    yml = (Path(__file__).resolve().parent.parent / ".github/workflows/poster.yml").read_text()
    stunden = {int(h) for h in yml.split('cron: "1 ')[1].split(" ")[0].split(",")}
    for slot in (8, 13, 19):
        assert slot - 1 in stunden and slot - 2 in stunden


def test_env_setzen_ersetzt_und_ergaenzt(tmp_path):
    from poster.iglogin import env_setzen
    env = tmp_path / ".env"
    env.write_text("IG_ACCESS_TOKEN=alt\nBUFFER_API_KEY=x\n")
    env_setzen(env, {"IG_ACCESS_TOKEN": "neu\\1", "IG_USER_ID": "17"})
    assert env.read_text() == "IG_ACCESS_TOKEN=neu\\1\nBUFFER_API_KEY=x\nIG_USER_ID=17\n"


def test_login_link():
    from poster.iglogin import login_link
    url = login_link("123", "https://mimobaby1.github.io/auto-poster/callback.html")
    assert "client_id=123" in url and "instagram_business_content_publish" in url
    assert "redirect_uri=https%3A%2F%2Fmimobaby1.github.io%2Fauto-poster%2Fcallback.html" in url
