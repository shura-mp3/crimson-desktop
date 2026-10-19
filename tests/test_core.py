"""Unit tests for the parts that don't need D-Bus or a display:  python3 -m unittest discover -s tests"""

import json
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from crimson import lrc, lyrics  # noqa: E402
from crimson.mpris import Track  # noqa: E402


class LrcTests(unittest.TestCase):
    def test_lines_tags_offset(self):
        p = lrc.parse("[ar:X]\n[offset:+250]\n[00:01.50]one\n[00:03.2]two\n[01:02.123]three\n")
        self.assertEqual([l["t"] for l in p["lines"]], [1500, 3200, 62123])
        self.assertEqual(p["offset"], 250)
        self.assertEqual(p["tags"]["ar"], "X")
        self.assertFalse(p["has_words"])

    def test_repeated_stamps_sorted(self):
        p = lrc.parse("[00:20.00][00:05.00]chorus\n[00:10.00]verse")
        self.assertEqual([(l["t"], l["text"]) for l in p["lines"]], [(5000, "chorus"), (10000, "verse"), (20000, "chorus")])

    def test_enhanced_word_stamps(self):
        p = lrc.parse("[00:04.00]<00:04.00>You <00:04.60>could <00:05.20>be <00:07.00>")
        ln = p["lines"][0]
        self.assertTrue(p["has_words"])
        self.assertEqual(ln["text"], "You could be")
        self.assertEqual(ln["w"][0], [4000, "You "])
        self.assertEqual(ln["w"][-1], [5200, "be ", 7000])  # trailing stamp = end time

    def test_no_invented_word_timing(self):
        p = lrc.parse("[00:01.00]plain line only")
        self.assertIsNone(p["lines"][0]["w"])

    def test_line_index(self):
        lines = lrc.parse("[00:01.00]a\n[00:02.00]b\n[00:03.00]c")["lines"]
        self.assertEqual(lrc.line_index(lines, 500), -1)
        self.assertEqual(lrc.line_index(lines, 1000), 0)
        self.assertEqual(lrc.line_index(lines, 2999), 1)
        self.assertEqual(lrc.line_index(lines, 99999), 2)

    def test_garbage_is_not_synced(self):
        r = lyrics.from_lrc_text("just some words\nno timestamps", "x")
        self.assertEqual(r["status"], "plain")


class MatchingTests(unittest.TestCase):
    def test_clean_title(self):
        self.assertEqual(lyrics.clean_title("Song - Remastered 2011"), "Song")
        self.assertEqual(lyrics.clean_title("Song (feat. Someone)"), "Song")
        self.assertEqual(lyrics.clean_title("Song (Live at Wembley)"), "Song")
        self.assertEqual(lyrics.clean_title("Mr. Brightside"), "Mr. Brightside")

    def test_primary_artist(self):
        self.assertEqual(lyrics.primary_artist("A, B"), "A")
        self.assertEqual(lyrics.primary_artist("A & B"), "A")
        self.assertEqual(lyrics.primary_artist("Simon & Garfunkel".replace(" & ", " and ")), "Simon and Garfunkel")

    def test_norm_accents(self):
        self.assertEqual(lyrics.norm("Beyoncé!"), "beyonce")


class SpotifyMetadataTests(unittest.TestCase):
    def test_from_metadata(self):
        t = Track.from_metadata({
            "mpris:trackid": ("o", "/com/spotify/track/abc"), "xesam:title": ("s", "T"),
            "xesam:artist": ("as", ["A", "B"]), "xesam:album": ("s", "Al"),
            "mpris:length": ("t", 215_000_000), "mpris:artUrl": ("s", "https://open.spotify.com/image/ff00"),
        })
        self.assertEqual((t.title, t.artist, t.album, t.length_ms), ("T", "A, B", "Al", 215000))
        self.assertEqual(t.art_url, "https://i.scdn.co/image/ff00")
        self.assertFalse(t.is_ad)
        self.assertTrue(Track(id="spotify:ad:123").is_ad)


class LyricsServiceTests(unittest.TestCase):
    """Against the mock LRCLIB server; local .lrc files; cache."""

    @classmethod
    def setUpClass(cls):
        import mock_lrclib
        cls.srv = HTTPServer(("127.0.0.1", 0), mock_lrclib.H)
        cls.srv.hits = []
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.tmp = tempfile.TemporaryDirectory()
        from crimson import paths
        paths.LYRICS_CACHE = Path(cls.tmp.name) / "cache"
        paths.USER_LYRICS_DIR = Path(cls.tmp.name) / "user"
        paths.USER_LYRICS_DIR.mkdir()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()

    def svc(self, **kw):
        cfg = {"lyrics": {"lrclib": True, "lrclib_url": f"http://127.0.0.1:{self.srv.server_port}",
                          "local_dirs": [], "duration_tolerance": 3, "negative_cache_hours": 24, **kw}}
        return lyrics.LyricsService(cfg)

    def test_lrclib_synced_and_cached(self):
        s = self.svc()
        r = s.lookup("Crimson Test", "Everything You Are", "Signal Lost", 30_000)
        self.assertEqual(r["status"], "synced")
        self.assertTrue(r["has_words"])
        hits = len(self.srv.hits)
        r2 = s.lookup("Crimson Test", "Everything You Are", "Signal Lost", 30_000)
        self.assertEqual(r2["status"], "synced")
        self.assertIn("cached", r2["source"])
        self.assertEqual(len(self.srv.hits), hits)  # served from cache

    def test_duration_mismatch_rejected(self):
        r = self.svc().lookup("Crimson Test", "Everything You Are", "Other", 200_000)
        self.assertNotEqual(r["status"], "synced")

    def test_local_file_wins(self):
        (Path(self.tmp.name) / "user" / "Some Artist - Local Song.lrc").write_text("[00:01.00]from disk")
        r = self.svc().lookup("Some Artist", "Local Song", "", 100_000)
        self.assertEqual(r["status"], "synced")
        self.assertTrue(r["source"].startswith("local:"))

    def test_network_error_not_cached(self):
        s = self.svc(lrclib_url="http://127.0.0.1:9")  # nothing listens on the discard port
        r = s.lookup("Nobody", "Nothing", "", 100_000)
        self.assertEqual(r["status"], "error")
        self.assertIsNone(s._cache_get(s._cache_key("Nobody", "Nothing", 100_000)))


class MonitorParsingTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("dm", ROOT / "scripts" / "detect-monitors.py")
        self.dm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.dm)

    def test_json(self):
        raw = json.dumps({"outputs": [
            {"name": "DP-2", "enabled": True, "connected": True, "priority": 2, "pos": {"x": 1920, "y": 0}, "scale": 2,
             "rotation": 1, "currentModeId": "a", "modes": [{"id": "a", "refreshRate": 144, "size": {"width": 3840, "height": 2160}}]},
            {"name": "DP-1", "enabled": True, "connected": True, "priority": 1, "pos": {"x": 0, "y": 0}, "scale": 1,
             "rotation": 2, "currentModeId": "b", "modes": [{"id": "b", "refreshRate": 60, "size": {"width": 1920, "height": 1080}}]},
        ]})
        outs = self.dm.from_json(raw)
        dp2 = next(o for o in outs if o["name"] == "DP-2")
        dp1 = next(o for o in outs if o["name"] == "DP-1")
        self.assertEqual((dp2["logical_width"], dp2["logical_height"]), (1920, 1080))
        self.assertEqual((dp1["logical_width"], dp1["logical_height"]), (1080, 1920))  # rotated
        self.assertTrue(dp1["primary"])

    def test_text_fallback(self):
        raw = ("Output: 1 DP-1 enabled connected priority 1 DisplayPort Modes: 1:2560x1440@165*! 2:1920x1080@60 "
               "Geometry: 0,0 2560x1440 Scale: 1 Rotation: 1\n"
               "Output: 2 HDMI-A-1 enabled connected priority 2 HDMI Modes: 1:1920x1080@75*! "
               "Geometry: 2560,180 1920x1080 Scale: 1 Rotation: 1\n")
        outs = self.dm.from_text(raw)
        self.assertEqual([o["name"] for o in outs], ["DP-1", "HDMI-A-1"])
        self.assertEqual(outs[1]["x"], 2560)
        self.assertEqual(outs[0]["refresh"], 165.0)


if __name__ == "__main__":
    unittest.main()
