"""Headless UI tests driving the real Textual app with its test pilot (safe mode: no crimson-core).

    terminal-os/.venv/bin/python -m unittest discover -s terminal-os/tests
"""

import asyncio
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _sandbox  # noqa: E402  (must precede the crimson imports)

from textual.widgets import DataTable, Input, Static, Switch, TabbedContent  # noqa: E402

from crimson_tos.app import CrimsonApp  # noqa: E402
from crimson_tos.screens.dialogs import Confirm, Help, Prompt  # noqa: E402
from crimson_tos.services import settings as settings_svc  # noqa: E402

MODULES = ["home", "music", "monitor", "files", "commands", "theme"]


def text_of(widget) -> str:
    c = widget.content
    return getattr(c, "plain", None) or str(c)


class UITest(unittest.TestCase):
    def run_app(self, scenario, size=(140, 40), **kw):
        async def main():
            app = CrimsonApp(animation=False, safe_mode=True, **kw)
            async with app.run_test(size=size) as pilot:
                await pilot.pause(0.5)
                await scenario(app, pilot)
            return app
        return asyncio.run(main())


class NavigationTests(UITest):
    def test_number_keys_switch_modules(self):
        async def s(app, pilot):
            self.assertEqual(app.current_mode, "home")
            for i, m in enumerate(MODULES, 1):
                if app.current_mode == "commands":       # the search box has focus there; F-keys always work
                    await pilot.press(f"f{i}")
                else:
                    await pilot.press(str(i))
                await pilot.pause(0.2)
                self.assertEqual(app.current_mode, m)
        self.run_app(s)

    def test_typing_digits_in_search_does_not_switch(self):
        async def s(app, pilot):
            await pilot.press("5")
            await pilot.pause(0.3)
            await pilot.press("6")
            self.assertEqual(app.current_mode, "commands")
            self.assertEqual(app.screen.query_one(Input).value, "6")
            await pilot.press("alt+1")
            await pilot.pause(0.2)
            self.assertEqual(app.current_mode, "home")
        self.run_app(s)

    def test_help_overlay_opens_and_closes(self):
        async def s(app, pilot):
            await pilot.press("question_mark")
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, Help)
            await pilot.press("escape")
            await pilot.pause(0.2)
            self.assertNotIsInstance(app.screen, Help)
        self.run_app(s)

    def test_command_palette(self):
        async def s(app, pilot):
            await pilot.press("slash")
            await pilot.pause(0.3)
            self.assertIn("CommandPalette", type(app.screen).__name__)
            await pilot.press(*"monitor")
            await pilot.pause(0.5)
            await pilot.press("enter")
            await pilot.pause(0.5)
            self.assertEqual(app.current_mode, "monitor")
        self.run_app(s)

    def test_start_module_and_quit(self):
        async def s(app, pilot):
            self.assertEqual(app.current_mode, "music")
            await pilot.press("ctrl+q")
            await pilot.pause(0.2)
        app = self.run_app(s, module="music")
        self.assertEqual(app.return_code, 0)

    def test_confirm_quit_setting(self):
        async def s(app, pilot):
            app.settings.confirm_quit = True
            await pilot.press("ctrl+q")
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, Confirm)
            await pilot.press("n")
            await pilot.pause(0.2)
            self.assertTrue(app.is_running)
            app.settings.confirm_quit = False
        self.run_app(s)


class LayoutTests(UITest):
    def test_every_module_renders_at_many_sizes(self):
        for size in [(60, 20), (80, 24), (100, 30), (160, 46), (220, 60)]:
            with self.subTest(size=size):
                async def s(app, pilot):
                    for i in range(1, 7):
                        await pilot.press(f"f{i}")
                        await pilot.pause(0.25)
                        self.assertEqual(app.current_mode, MODULES[i - 1])
                self.run_app(s, size=size)

    def test_home_grid_adapts(self):
        async def s(app, pilot):
            grid = app.screen.query_one("#home-grid")
            self.assertTrue(grid.has_class("cols-1"))
        self.run_app(s, size=(90, 30))


class OfflineTests(UITest):
    def test_music_explains_missing_core(self):
        async def s(app, pilot):
            await pilot.pause(0.3)
            now = text_of(app.screen.query_one("#now", Static))
            lyrics = text_of(app.screen.query_one("#lyrics", Static))
            self.assertIn("CRIMSON-CORE OFFLINE", now)
            self.assertIn("crimsonctl start", lyrics)
            self.assertFalse(app.core.connected)
        self.run_app(s, module="music")

    def test_home_shows_real_identity(self):
        async def s(app, pilot):
            await pilot.pause(1.2)
            ident = text_of(app.screen.query_one("#identity", Static))
            self.assertIn(app.metrics.static["user"], ident)
            self.assertIn("idle (no audio)", app.screen.query_one("#signal").border_subtitle)
        self.run_app(s)


class FilesTests(UITest):
    def test_create_folder_and_trash_with_confirmation(self):
        home = _sandbox.HOME

        async def s(app, pilot):
            await pilot.press("4")
            await pilot.pause(0.4)
            app.screen.query_one("#file-table", DataTable).focus()
            await pilot.press("n")
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, Prompt)
            await pilot.press(*"crimson-test-dir", "enter")
            await pilot.pause(0.4)
            self.assertTrue((home / "crimson-test-dir").is_dir())
            table = app.screen.query_one("#file-table", DataTable)
            self.assertEqual(app.screen.current().name, "crimson-test-dir")   # new folder gets selected
            row = table.cursor_row
            await pilot.press("d")
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, Confirm)
            await pilot.press("enter")                  # Cancel has focus by default
            await pilot.pause(0.2)
            self.assertTrue((home / "crimson-test-dir").exists())
            table.move_cursor(row=row)
            await pilot.press("d")
            await pilot.pause(0.2)
            await pilot.press("y")
            await pilot.pause(0.4)
            self.assertFalse((home / "crimson-test-dir").exists())
            self.assertTrue((home / ".local/share/Trash/files/crimson-test-dir").is_dir())
        self.run_app(s)


class MonitorTests(UITest):
    def test_terminate_own_process_after_confirmation(self):
        victim = subprocess.Popen(["sleep", "60"])
        self.addCleanup(lambda: victim.poll() is None and victim.kill())

        async def s(app, pilot):
            await pilot.press("3")
            await pilot.pause(0.4)
            app.screen.query_one("#mon-tabs", TabbedContent).active = "t-proc"
            await pilot.pause(0.6)
            app.screen.query_one("#proc-filter", Input).value = str(victim.pid)
            await pilot.pause(0.4)
            table = app.screen.query_one("#proc-table", DataTable)
            self.assertEqual(table.row_count, 1)
            table.focus()
            await pilot.press("k")
            await pilot.pause(0.2)
            self.assertIsInstance(app.screen, Confirm)
            await pilot.press("escape")
            await pilot.pause(0.2)
            self.assertIsNone(victim.poll())            # cancelled → still alive
            await pilot.press("k")
            await pilot.pause(0.2)
            await pilot.press("y")
            await pilot.pause(0.3)
        self.run_app(s)
        self.assertEqual(victim.wait(timeout=5), -15)  # SIGTERM

    def test_refuses_critical_process(self):
        async def s(app, pilot):
            await pilot.press("3")
            await pilot.pause(0.3)
            app.screen.query_one("#mon-tabs", TabbedContent).active = "t-proc"
            await pilot.pause(0.5)
            app.screen.query_one("#proc-filter", Input).value = str(os.getpid())
            await pilot.pause(0.3)
            app.screen.query_one("#proc-table", DataTable).focus()
            await pilot.press("k")
            await pilot.pause(0.2)
            self.assertNotIsInstance(app.screen, Confirm)   # own UI process: refused before asking
        self.run_app(s)


class ThemeTests(UITest):
    def test_toggle_persists_settings(self):
        async def s(app, pilot):
            await pilot.press("6")
            await pilot.pause(0.4)
            sw = app.screen.query_one("#sw-clock_24h", Switch)
            sw.value = not sw.value
            await pilot.pause(0.3)
            self.assertEqual(app.settings.clock_24h, sw.value)
            saved, problems = settings_svc.load(settings_svc.SETTINGS_FILE)
            self.assertEqual(saved.clock_24h, sw.value)
            self.assertEqual(problems, [])
        self.run_app(s)

    def test_compact_mode_hides_decoration(self):
        async def s(app, pilot):
            self.assertTrue(app.screen.query_one("#signal").display)
            app.settings.compact = True
            app.apply_settings()
            await pilot.pause(0.3)
            self.assertFalse(app.screen.query_one("#signal").display)
            app.settings.compact = False
            app.apply_settings()
        self.run_app(s)

    def test_settings_file_lives_in_sandbox(self):
        self.assertTrue(str(settings_svc.SETTINGS_FILE).startswith(str(_sandbox.HOME)))


if __name__ == "__main__":
    unittest.main()
