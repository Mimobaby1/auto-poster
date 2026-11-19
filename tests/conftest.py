import json
import shutil
from pathlib import Path

import pytest

from poster import config as konf

ROOT = Path(__file__).resolve().parent.parent

CSV = """﻿Tag;Ziel;Datei;Video;Hook (im Bild);Lyrics;Songstelle;Länge (s);Konzept;Song-Start;Caption-Vorschlag
1;insta_test_1;tag_01/insta_test_1.mp4;test_01;h1;keine;x;6;Hook;0;cap eins
1;insta_test_2;tag_01/insta_test_2.mp4;test_02;h2;keine;x;6;Hook;0;cap zwei
1;insta_test_3;tag_01/insta_test_3.mp4;test_03;h3;keine;x;6;Hook;0;cap drei
1;tiktok_acc1;tag_01/tiktok_acc1.mp4;test_01;h1;keine;x;6;Hook;0;cap eins
1;tiktok_acc2;tag_01/tiktok_acc2.mp4;test_02;h2;keine;x;6;Hook;0;cap zwei
1;tiktok_acc3;tag_01/tiktok_acc3.mp4;test_03;h3;keine;x;6;Hook;0;cap drei
2;insta_test_1;tag_02/insta_test_1.mp4;test_04;h4;keine;x;6;Hook;0;cap vier
2;insta_test_2;tag_02/insta_test_2.mp4;test_05;h5;keine;x;6;Hook;0;cap fünf
2;insta_test_3;tag_02/insta_test_3.mp4;test_06;h6;keine;x;6;Hook;0;cap sechs
2;tiktok_acc1;tag_02/tiktok_acc1.mp4;test_04;h4;keine;x;6;Hook;0;cap vier
2;tiktok_acc2;tag_02/tiktok_acc2.mp4;test_05;h5;keine;x;6;Hook;0;cap fünf
2;tiktok_acc3;tag_02/tiktok_acc3.mp4;test_06;h6;keine;x;6;Hook;0;cap sechs
"""


@pytest.fixture
def cfg(tmp_path):
    shutil.copy(ROOT / "config.json", tmp_path / "config.json")
    data = json.loads((tmp_path / "config.json").read_text())
    data.update(start_datum="2026-12-01", aktiv=True, media_base_url="https://x.github.io/repo",
                tiktok_kanaele={"tiktok_acc1": "k1", "tiktok_acc2": "k2", "tiktok_acc3": "k3"})
    (tmp_path / "config.json").write_text(json.dumps(data))
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos" / "upload_plan.csv").write_text(CSV, encoding="utf-8")
    return konf.laden(tmp_path / "config.json")
