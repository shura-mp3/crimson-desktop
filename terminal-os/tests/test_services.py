"""Unit tests for the Crimson Terminal OS services (no terminal or display needed).

    terminal-os/.venv/bin/python -m unittest discover -s terminal-os/tests
"""

import getpass
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _sandbox  # noqa: E402,F401  (must precede the crimson imports)

from crimson_tos.services import commands, files, metrics, settings  # noqa: E402
from crimson_tos.widgets import glyphs  # noqa: E402


class Tmp(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)


class SettingsTests(Tmp):
    def test_round_trip(self):
        p = self.tmp / "s.toml"
        s = settings.Settings(performance="high", default_module="music", clock_24h=False, accent="rose")
        settings.save(s, p)
        loaded, problems = settings.load(p)
        self.assertEqual(problems, [])
        self.assertEqual(loaded, s)

    def test_invalid_values_fall_back_with_problems(self):
        p = self.tmp / "s.toml"
        p.write_text('performance = "ludicrous"\ncompact = "yes"\nbogus = 1\ndefault_module = "files"\n')
        s, problems = settings.load(p)
        self.assertEqual(s.performance, "auto")
        self.assertFalse(s.compact)
        self.assertEqual(s.default_module, "files")
        self.assertEqual(len(problems), 3)

    def test_corrupt_file_uses_defaults(self):
        p = self.tmp / "s.toml"
        p.write_text("this is = = not toml")
        s, problems = settings.load(p)
        self.assertEqual(s, settings.Settings())
        self.assertIn("unreadable", problems[0])

    def test_missing_file_is_fine(self):
        self.assertEqual(settings.load(self.tmp / "nope.toml"), (settings.Settings(), []))

    def test_strings_are_escaped(self):
        self.assertEqual(settings._toml_value('a"b\\c'), '"a\\"b\\\\c"')


class FileTests(Tmp):
    def test_list_sort_hidden(self):
        (self.tmp / "b.txt").write_text("xx")
        (self.tmp / "a.txt").write_text("xxxxxxxx")
        (self.tmp / ".hidden").write_text("")
        (self.tmp / "zdir").mkdir()
        names = [e.name for e in files.list_dir(self.tmp)]
        self.assertEqual(names, ["zdir", "a.txt", "b.txt"])          # folders first, hidden excluded
        self.assertIn(".hidden", [e.name for e in files.list_dir(self.tmp, show_hidden=True)])
        self.assertEqual([e.name for e in files.list_dir(self.tmp, sort="size")][1], "a.txt")

    def test_names_validated(self):
        for bad in ("", " ", ".", "..", "a/b", "x\x00y"):
            with self.assertRaises(files.FileOpError):
                files.valid_name(bad)

    def test_create_never_clobbers(self):
        f = files.make_file(self.tmp, "n.txt")
        f.write_text("keep me")
        with self.assertRaises(files.FileOpError):
            files.make_file(self.tmp, "n.txt")
        self.assertEqual(f.read_text(), "keep me")
        files.make_dir(self.tmp, "d")
        with self.assertRaises(files.FileOpError):
            files.make_dir(self.tmp, "d")

    def test_rename_copy_move_refuse_overwrite_and_self(self):
        a = self.tmp / "a.txt"
        a.write_text("A")
        (self.tmp / "b.txt").write_text("B")
        with self.assertRaises(files.FileOpError):
            files.rename(a, "b.txt")
        d = files.make_dir(self.tmp, "d")
        c = files.copy(a, d)
        self.assertEqual(c.read_text(), "A")
        with self.assertRaises(files.FileOpError):
            files.copy(a, d)
        with self.assertRaises(files.FileOpError):
            files.copy(self.tmp, d)                                    # folder into itself
        with self.assertRaises(files.FileOpError):
            files.move(self.tmp, d)                                    # folder into itself
        m = files.move(self.tmp / "b.txt", d)
        self.assertEqual(m.read_text(), "B")
        self.assertFalse((self.tmp / "b.txt").exists())

    def test_trash_is_freedesktop_compatible(self):
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.tmp / "data")}):
            f = self.tmp / "gone.txt"
            f.write_text("bye")
            files.trash(f)
            f.write_text("again")
            files.trash(f)                                             # name clash → gone.txt.2
            tdir = self.tmp / "data" / "Trash"
            self.assertFalse(f.exists())
            self.assertEqual(sorted(p.name for p in (tdir / "files").iterdir()), ["gone.txt", "gone.txt.2"])
            info = (tdir / "info" / "gone.txt.trashinfo").read_text()
            self.assertTrue(info.startswith("[Trash Info]\nPath="))
            self.assertIn("DeletionDate=", info)

    def test_preview_strips_terminal_control_sequences(self):
        f = self.tmp / "evil.txt"
        f.write_text("hello\x1b]0;pwned\x07 \x1b[31mred\x1b[0m \x1b[2J\x07bell\x9b")
        kind, text = files.preview(files.list_dir(self.tmp)[0])
        self.assertEqual(kind, "text")
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)
        self.assertNotIn("\x9b", text)
        self.assertIn("hello", text)
        self.assertIn("red", text)

    def test_preview_kinds(self):
        (self.tmp / "a.json").write_text('{"b": 1}')
        (self.tmp / "b.md").write_text("# hi")
        (self.tmp / "c.py").write_text("print(1)")
        (self.tmp / "d.bin").write_bytes(b"\x00\x01\x02")
        (self.tmp / "e.sh").write_text("rm -rf /\n")             # shown, never executed
        kinds = {e.name: files.preview(e)[0] for e in files.list_dir(self.tmp)}
        self.assertEqual(kinds, {"a.json": "json", "b.md": "markdown", "c.py": "code", "d.bin": "binary", "e.sh": "code"})

    def test_preview_is_size_capped(self):
        f = self.tmp / "big.txt"
        f.write_text("x" * (files.MAX_PREVIEW * 3))
        self.assertLessEqual(len(files.preview(files.list_dir(self.tmp)[0])[1]), files.MAX_PREVIEW)


class CommandTests(Tmp):
    def test_fuzzy_ranking(self):
        cmds = [commands.Command("1", "Firefox", "Apps"), commands.Command("2", "System Monitor", "Apps"),
                commands.Command("3", "Files", "Crimson", keywords="dolphin")]
        self.assertEqual(commands.search("fire", cmds)[0].title, "Firefox")
        self.assertEqual(commands.search("smon", cmds)[0].title, "System Monitor")
        self.assertEqual(commands.search("dolphin", cmds)[0].title, "Files")
        self.assertEqual(commands.search("zzzz", cmds), [])
        self.assertEqual(len(commands.search("", cmds)), 3)

    def test_custom_commands_are_argv_only_and_unprivileged(self):
        p = self.tmp / "c.toml"
        p.write_text('[[command]]\ntitle = "ok"\nargv = ["echo", "~/x"]\n'
                     '[[command]]\nargv = "echo; rm -rf ~"\n'
                     '[[command]]\nargv = ["sudo", "dnf", "update"]\n'
                     '[[command]]\nargv = ["pkexec", "x"]\n')
        cmds, problems = commands.custom_commands(p)
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].argv, ["echo", os.path.expanduser("~/x")])
        self.assertEqual(len(problems), 3)

    def test_custom_commands_bad_toml(self):
        p = self.tmp / "c.toml"
        p.write_text("[[command")
        self.assertEqual(commands.custom_commands(p)[0], [])

    def test_desktop_entries_respect_visibility_rules(self):
        apps = self.tmp / "applications"
        apps.mkdir()
        (apps / "good.desktop").write_text("[Desktop Entry]\nType=Application\nName=Good App\nExec=true %U\n")
        (apps / "hidden.desktop").write_text("[Desktop Entry]\nType=Application\nName=Hidden\nExec=true\nNoDisplay=true\n")
        (apps / "gnome.desktop").write_text("[Desktop Entry]\nType=Application\nName=Gnomey\nExec=true\nOnlyShowIn=GNOME;\n")
        (apps / "missing.desktop").write_text("[Desktop Entry]\nType=Application\nName=Missing\nExec=x\nTryExec=/nonexistent/x\n")
        with mock.patch.object(commands, "_data_dirs", return_value=[self.tmp]), \
                mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
            names = [c.title for c in commands.desktop_entries()]
        self.assertEqual(names, ["Good App"])

    def test_builtins_have_unique_ids(self):
        ids = [c.id for c in commands.builtin_commands()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_run_argv_missing_binary(self):
        with self.assertRaises(FileNotFoundError):
            commands.run_argv(["/nonexistent/binary"])


class MetricsTests(unittest.TestCase):
    def test_human_formatting(self):
        self.assertEqual(metrics.human_bytes(None), "n/a")
        self.assertEqual(metrics.human_bytes(512), "512B")
        self.assertEqual(metrics.human_bytes(1536, rate=True), "1.5K/s")
        self.assertEqual(metrics.human_bytes(3 * 1024 ** 3), "3.0G")
        self.assertEqual(metrics.human_duration(59), "0m")
        self.assertEqual(metrics.human_duration(3 * 86400 + 2 * 3600 + 5 * 60), "3d 2h 5m")

    def test_can_terminate_safety(self):
        me = getpass.getuser()
        self.assertFalse(metrics.can_terminate({"pid": 1, "name": "x", "user": me})[0])
        self.assertFalse(metrics.can_terminate({"pid": os.getpid(), "name": "x", "user": me})[0])
        self.assertFalse(metrics.can_terminate({"pid": 99999, "name": "plasmashell", "user": me})[0])
        self.assertFalse(metrics.can_terminate({"pid": 99999, "name": "x", "user": "?"})[0])
        self.assertTrue(metrics.can_terminate({"pid": 99999, "name": "firefox", "user": me})[0])
        with mock.patch("os.geteuid", return_value=1000):
            self.assertFalse(metrics.can_terminate({"pid": 99999, "name": "firefox", "user": "someone-else"})[0])

    def test_sample_and_lists(self):
        m = metrics.Metrics()
        s = m.sample()
        self.assertGreaterEqual(s.cpu, 0)
        self.assertGreater(s.mem_total, 0)
        self.assertIsInstance(m.disks(), list)
        self.assertTrue(all(d["fs"] not in metrics.PSEUDO_FS for d in m.disks()))
        procs = m.processes()
        self.assertTrue(any(p["pid"] == os.getpid() for p in procs))


class GlyphTests(unittest.TestCase):
    def test_big_text_shape(self):
        t = glyphs.big_text("12:34")
        rows = t.plain.split("\n")
        self.assertEqual(len(rows), 5)
        self.assertEqual(len({len(r) for r in rows}), 1)
        self.assertEqual(len(rows[0]), glyphs.big_width("12:34"))
        self.assertTrue(glyphs.fit_big("HI", 40))
        self.assertFalse(glyphs.fit_big("A VERY LONG LYRIC LINE INDEED", 20))

    def test_graph_fixed_scale(self):
        low = glyphs.graph([3, 3, 3], 3, 4, vmax=100).plain
        self.assertNotIn("█", low)                                      # 3% must not look like 100%
        full = glyphs.graph([100, 100, 100], 3, 4, vmax=100).plain
        self.assertEqual(full.count("█"), 12)

    def test_spectrum_dimensions_and_silence(self):
        t = glyphs.spectrum([0.5] * 48, 30, 4)
        self.assertEqual(len(t.plain.split("\n")), 4)
        silent = glyphs.spectrum([], 30, 4).plain
        self.assertNotIn("█", silent)

    def test_meter_unknown(self):
        self.assertEqual(len(glyphs.meter(None, 10).plain), 10)
        self.assertEqual(len(glyphs.meter(0.5, 10).plain), 10)

    def test_fmt_time(self):
        self.assertEqual(glyphs.fmt_time(65_000), "1:05")
        self.assertEqual(glyphs.fmt_time(0), "0:00")


if __name__ == "__main__":
    unittest.main()
