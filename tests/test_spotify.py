"""Tests for the Spicetify integration helpers and the loopback bridge protocol."""

import asyncio
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crimson import bridge, spotify  # noqa: E402


class BridgeProtocolTests(unittest.TestCase):
    def test_accept_key_rfc6455_vector(self):
        self.assertEqual(bridge.accept_key("dGhlIHNhbXBsZSBub25jZQ=="), "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")

    def test_encode_text_lengths(self):
        self.assertEqual(bridge.encode_text("hi")[:2], b"\x81\x02")
        self.assertEqual(bridge.encode_text("x" * 200)[:4], b"\x81\x7e\x00\xc8")
        self.assertEqual(bridge.encode_text("x" * 70000)[:2], b"\x81\x7f")

    def _frame(self, payload: bytes, masked=True, fin=True, opcode=1):
        mask = b"\x01\x02\x03\x04"
        head = bytes([(0x80 if fin else 0) | opcode])
        n = len(payload)
        head += bytes([(0x80 if masked else 0) | (n if n < 126 else 126)]) + (struct.pack("!H", n) if n >= 126 else b"")
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload)) if masked else payload
        return head + (mask if masked else b"") + body

    def _read(self, data: bytes):
        async def go():
            r = asyncio.StreamReader()
            r.feed_data(data)
            r.feed_eof()
            return await bridge.read_frame(r)
        return asyncio.run(go())

    def test_read_masked_frame(self):
        self.assertEqual(self._read(self._frame(b'{"cmd":"ping"}')), (1, b'{"cmd":"ping"}'))

    def test_reject_unmasked_fragmented_oversized(self):
        for data in (self._frame(b"x", masked=False), self._frame(b"x", fin=False), self._frame(b"x" * (bridge.MAX_FRAME + 1))):
            with self.assertRaises(ConnectionError):
                self._read(data)

    def test_bridge_command_allowlist(self):
        self.assertEqual(bridge.BRIDGE_COMMANDS, {"sub", "offset", "ping"})
        self.assertNotIn("sys", bridge.BRIDGE_TOPICS)


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_apps_state(self):
        apps = self.d / "Apps"
        apps.mkdir()
        self.assertEqual(spotify.apps_state(self.d), "invalid")
        (apps / "xpui.spa").write_text("x")
        self.assertEqual(spotify.apps_state(self.d), "stock")
        (apps / "xpui").mkdir()
        self.assertEqual(spotify.apps_state(self.d), "mixed")
        (apps / "xpui.spa").unlink()
        self.assertEqual(spotify.apps_state(self.d), "applied")

    def test_prefs_version_reads_only_version(self):
        p = self.d / "prefs"
        p.write_text('autologin.username="someone"\napp.last-launched-version="1.2.93.564.g1"\n')
        self.assertEqual(spotify.prefs_version(p), "1.2.93.564.g1")
        self.assertEqual(spotify.prefs_version(self.d / "missing"), "")

    def test_tree_hash_ignores_marker(self):
        (self.d / "a.css").write_text("x")
        h1 = spotify.tree_hash(self.d)
        (self.d / spotify.MARKER).write_text("owned")
        self.assertEqual(h1, spotify.tree_hash(self.d))
        (self.d / "a.css").write_text("y")
        self.assertNotEqual(h1, spotify.tree_hash(self.d))

    def test_choose_target_refuses_to_guess(self):
        a = {"method": "flatpak-system", "path": "/a"}
        b = {"method": "rpm", "path": "/b"}
        self.assertEqual(spotify.choose_target([a], None), a)
        self.assertEqual(spotify.choose_target([a, b], "rpm"), b)
        with self.assertRaises(SystemExit):
            spotify.choose_target([a, b], None)
        with self.assertRaises(SystemExit):
            spotify.choose_target([], None)

    def test_project_theme_files_present(self):
        for f in ("color.ini", "user.css", "theme.js"):
            self.assertTrue((spotify.SRC_THEME / f).is_file(), f)
        for f in ("manifest.json", "index.js"):
            self.assertTrue((spotify.SRC_APP / f).is_file(), f)


if __name__ == "__main__":
    unittest.main()
