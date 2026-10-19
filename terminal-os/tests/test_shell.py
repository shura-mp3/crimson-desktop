"""Konsole integration tests: the sh wrapper, crimson-autostart and the install/theme/restore scripts.

Everything runs in a throw-away $HOME with stub launchers/shells, inside a real pseudo-terminal so the
wrapper's tty checks behave exactly as in Konsole.   python3 -m unittest discover -s terminal-os/tests
"""

import os
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

TOS = Path(__file__).resolve().parent.parent
BIN = TOS / "bin"
SCRIPTS = TOS / "scripts"
KONSOLERC_ORIG = """[Desktop Entry]
DefaultProfile=Mine.profile

[MainWindow]
MenuBar=Disabled
State=AAAA/wAAAAD9

[KonsoleWindow]
RememberWindowSize=false
"""


class Sandbox:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="ctos-test-"))
        self.home = self.root / "home"
        self.bin = self.root / "stubs"
        for d in (self.home, self.bin, self.home / ".config", self.home / ".local" / "share" / "konsole"):
            d.mkdir(parents=True, exist_ok=True)
        self.out = self.root / "events.log"
        # stub user shell: logs that it started (and whether the guard variable leaked into it)
        self.shell = self._stub("fakeshell", f'echo "SHELL active=${{CRIMSON_TOS_ACTIVE:-}}" >> "{self.out}"\n')
        # stub `konsole`: forks (doesn't exec) the profile command, so the wrapper's parent is "konsole"
        self._stub("konsole", '"$@"\n')
        # a parent that is NOT konsole — stands in for Dolphin/Kate's embedded terminal panel
        self._stub("dolphin", '"$@"\n')

    def _stub(self, name, body):
        p = self.bin / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(0o755)
        return p

    def launcher(self, rc=0):
        return self._stub("crimson", f'echo "CRIMSON active=$CRIMSON_TOS_ACTIVE args=$*" >> "{self.out}"\nexit {rc}\n')

    def env(self, **extra):
        e = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin", "SHELL": str(self.shell),
             "TERM": "xterm-256color", "LANG": "C.UTF-8"}
        e.update({k: v for k, v in extra.items() if v is not None})
        return e

    def events(self):
        return self.out.read_text().splitlines() if self.out.exists() else []

    def run_pty(self, argv, env, timeout=10, typed=b""):
        """Run argv attached to a fresh pty (like a Konsole session); return the terminal output."""
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(argv[0], argv, env)
        if typed:
            os.write(fd, typed)
        out, end = b"", time.time() + timeout
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
            elif os.waitpid(pid, os.WNOHANG)[0]:
                break
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        os.close(fd)
        return out.decode(errors="replace")

    def wrapper(self, parent="konsole", typed=b"", **env):
        argv = [str(self.bin / parent), str(BIN / "crimson-konsole")] if parent else [str(BIN / "crimson-konsole")]
        return self.run_pty(argv, self.env(**env), typed=typed)

    def sh(self, *args, env=None, check=True):
        r = subprocess.run(list(args), env=env or self.env(), capture_output=True, text=True, timeout=120)
        if check and r.returncode != 0:
            raise AssertionError(f"{args} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return r

    @property
    def konsolerc(self):
        return self.home / ".config" / "konsolerc"

    @property
    def flag(self):
        return self.home / ".config" / "crimson-desktop" / "terminal-os.autostart-disabled"

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.addCleanup(self.s.cleanup)

    def launch_env(self, rc=0, **extra):
        return dict(CRIMSON_TOS_LAUNCHER=str(self.s.launcher(rc)), **extra)

    def test_normal_konsole_session_runs_crimson_then_shell(self):
        self.s.wrapper(**self.launch_env())
        ev = self.s.events()
        self.assertEqual(ev[0], "CRIMSON active=1 args=--from-konsole")
        self.assertEqual(ev[1], "SHELL active=")          # guard doesn't leak into the shell
        self.assertEqual(len(ev), 2)

    def test_bypass_variable(self):
        self.s.wrapper(**self.launch_env(CRIMSON_NO_AUTOSTART="1"))
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_recursion_guard(self):
        self.s.wrapper(**self.launch_env(CRIMSON_TOS_ACTIVE="1"))
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_disable_flag_file(self):
        self.s.flag.parent.mkdir(parents=True)
        self.s.flag.touch()
        self.s.wrapper(**self.launch_env())
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_ssh_session_untouched(self):
        self.s.wrapper(**self.launch_env(SSH_CONNECTION="10.0.0.2 5555 10.0.0.1 22"))
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_dumb_terminal_untouched(self):
        self.s.wrapper(**self.launch_env(TERM="dumb"))
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_embedded_terminal_panel_untouched(self):
        # Dolphin/Kate/KDevelop embed Konsole's part with the *default* profile; the parent isn't konsole
        self.s.wrapper(parent="dolphin", **self.launch_env())
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_noninteractive_untouched(self):
        env = self.s.env(**self.launch_env())
        r = subprocess.run([str(self.s.bin / "konsole"), str(BIN / "crimson-konsole")], env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_missing_launcher_falls_back_to_shell(self):
        out = self.s.wrapper(CRIMSON_TOS_LAUNCHER=str(self.s.root / "nope"))
        self.assertIn("launcher not found", out)
        self.assertEqual(self.s.events(), ["SHELL active="])

    def test_failure_message_counter_and_auto_pause(self):
        env = self.launch_env(rc=1)
        out = self.s.wrapper(**env)
        self.assertIn("exited with an error (code 1)", out)
        self.assertEqual(self.s.events()[-1], "SHELL active=")
        self.s.wrapper(**env)
        self.assertFalse(self.s.flag.exists())
        out = self.s.wrapper(**env)
        self.assertIn("auto-start paused after 3", out)
        self.assertTrue(self.s.flag.exists())
        n = len(self.s.events())
        self.s.wrapper(**env)                       # paused: goes straight to the shell
        self.assertEqual(self.s.events()[n:], ["SHELL active="])

    def test_quit_and_ctrl_c_are_not_failures(self):
        for rc in (0, 130):
            self.s.wrapper(**self.launch_env(rc=rc))
        fails = self.s.home / ".local" / "state" / "crimson-desktop" / "terminal-os.failures"
        self.assertFalse(fails.exists())

    def test_success_resets_failure_counter(self):
        self.s.wrapper(**self.launch_env(rc=1))
        fails = self.s.home / ".local" / "state" / "crimson-desktop" / "terminal-os.failures"
        self.assertEqual(fails.read_text().strip(), "1")
        self.s.wrapper(**self.launch_env(rc=0))
        self.assertFalse(fails.exists())

    def test_broken_python_falls_back_to_shell(self):
        # the real launcher with an interpreter that doesn't exist, then one without textual
        out = self.s.wrapper(CRIMSON_TOS_LAUNCHER=str(BIN / "crimson"), CRIMSON_TOS_PYTHON="/nonexistent/python")
        self.assertIn("exited with an error (code 3)", out)
        self.assertEqual(self.s.events(), ["SHELL active="])
        bare = shutil.which("python3")
        probe = subprocess.run([bare, "-c", "import textual"], capture_output=True)
        if probe.returncode == 0:
            self.skipTest("system python3 has textual; can't simulate a broken environment that way")
        out = self.s.wrapper(CRIMSON_TOS_LAUNCHER=str(BIN / "crimson"), CRIMSON_TOS_PYTHON=bare)
        self.assertIn("can't start", out)
        self.assertEqual(self.s.events(), ["SHELL active=", "SHELL active="])
        log = self.s.home / ".local" / "state" / "crimson-desktop" / "terminal-os.log"
        self.assertIn("import failed", log.read_text())

    def test_invalid_shell_falls_back(self):
        # a real interactive shell (passwd entry or /bin/sh) takes over: type into it, then leave
        out = self.s.wrapper(typed=b"echo FALLBACK-$((40+2)); exit\n", **self.launch_env(SHELL="/does/not/exist"))
        self.assertIn("FALLBACK-42", out)
        self.assertEqual(self.s.events(), ["CRIMSON active=1 args=--from-konsole"])

    def test_wrapper_is_posix_sh(self):
        if shutil.which("dash"):
            self.s.sh("dash", "-n", str(BIN / "crimson-konsole"))
            self.s.sh("dash", "-n", str(BIN / "crimson-autostart"))


class AutostartTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.addCleanup(self.s.cleanup)
        prof = self.s.home / ".local" / "share" / "konsole" / "Crimson OS.profile"
        prof.write_text("[General]\nName=Crimson OS\n")
        self.ctl = str(BIN / "crimson-autostart")

    def test_on_off_restores_konsolerc_byte_for_byte(self):
        self.s.konsolerc.write_text(KONSOLERC_ORIG)
        self.s.sh(self.ctl, "on")
        txt = self.s.konsolerc.read_text()
        self.assertIn("DefaultProfile=Crimson OS.profile", txt)
        self.assertIn("State=AAAA/wAAAAD9", txt)
        self.assertIn("ON", self.s.sh(self.ctl, "status").stdout)
        self.s.sh(self.ctl, "on")                   # idempotent: must not forget the real previous default
        self.s.sh(self.ctl, "off")
        self.assertEqual(self.s.konsolerc.read_text(), KONSOLERC_ORIG)
        self.assertTrue(self.s.flag.exists())
        self.assertIn("auto-start              : off", self.s.sh(self.ctl, "status").stdout)
        backups = list((self.s.home / ".local/state/crimson-desktop/backups/terminal-os").iterdir())
        self.assertEqual(len(backups), 2)           # one for on, one for off; the second `on` changed nothing
        self.assertTrue(all((b / "manifest.tsv").exists() for b in backups))

    def test_no_konsolerc_and_no_previous_default(self):
        self.s.sh(self.ctl, "on")
        self.assertEqual(self.s.konsolerc.read_text(), "[Desktop Entry]\nDefaultProfile=Crimson OS.profile\n")
        self.s.sh(self.ctl, "off")
        self.assertNotIn("DefaultProfile", self.s.konsolerc.read_text())

    def test_group_missing_is_appended(self):
        self.s.konsolerc.write_text("[MainWindow]\nMenuBar=Disabled\n")
        self.s.sh(self.ctl, "on")
        self.assertEqual(self.s.konsolerc.read_text(),
                         "[MainWindow]\nMenuBar=Disabled\n\n[Desktop Entry]\nDefaultProfile=Crimson OS.profile\n")

    def test_on_clears_flag_and_failures(self):
        self.s.flag.parent.mkdir(parents=True)
        self.s.flag.touch()
        st = self.s.home / ".local/state/crimson-desktop"
        st.mkdir(parents=True)
        (st / "terminal-os.failures").write_text("3\n")
        self.s.sh(self.ctl, "on")
        self.assertFalse(self.s.flag.exists())
        self.assertFalse((st / "terminal-os.failures").exists())

    def test_off_leaves_unrelated_default_alone(self):
        self.s.konsolerc.write_text(KONSOLERC_ORIG)
        self.s.sh(self.ctl, "off")
        self.assertEqual(self.s.konsolerc.read_text(), KONSOLERC_ORIG)

    def test_works_without_python(self):
        env = self.s.env()
        env["PATH"] = "/usr/bin/no-python-here:/bin"   # still has awk/sh/cp from /bin (usrmerge)
        if shutil.which("python3", path=env["PATH"]):
            env["PATH"] = str(self.s.bin)               # stub dir only — then add the bare tools
            for tool in ("awk", "cp", "mkdir", "date", "cat", "rm", "dirname", "readlink", "printf", "sed", "mv"):
                src = shutil.which(tool)
                if src:
                    os.symlink(src, self.s.bin / tool)
        self.assertIsNone(shutil.which("python3", path=env["PATH"]))
        self.s.konsolerc.write_text(KONSOLERC_ORIG)
        self.s.sh("/bin/sh", self.ctl, "on", env=env)
        self.s.sh("/bin/sh", self.ctl, "off", env=env)
        self.assertEqual(self.s.konsolerc.read_text(), KONSOLERC_ORIG)


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.s = Sandbox()
        self.addCleanup(self.s.cleanup)
        self.kdir = self.s.home / ".local" / "share" / "konsole"

    def test_theme_apply_never_overwrites_foreign_profile(self):
        mine = self.kdir / "Crimson.profile"
        mine.write_text("[General]\nName=Crimson\n# my own profile\n")
        other = self.kdir / "Work.profile"
        other.write_text("[General]\nName=Work\n")
        r = self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "apply", "--yes")
        self.assertIn("kept your existing", r.stderr)
        self.assertIn("# my own profile", mine.read_text())
        self.assertEqual(other.read_text(), "[General]\nName=Work\n")
        tos = (self.kdir / "Crimson OS.profile").read_text()
        self.assertIn(f"Command={self.s.home}/.local/bin/crimson-konsole", tos)
        self.assertIn("ColorScheme=Crimson", tos)
        self.assertTrue((self.kdir / "Crimson.colorscheme").exists())
        self.assertTrue(os.access(self.s.home / ".local/bin/crimson-konsole", os.X_OK))
        # re-apply is a no-op for our files
        before = (self.kdir / "Crimson OS.profile").stat().st_mtime_ns
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "apply", "--yes")
        self.assertEqual((self.kdir / "Crimson OS.profile").stat().st_mtime_ns, before)

    def test_force_backs_up_then_restore_is_idempotent(self):
        mine = self.kdir / "Crimson.profile"
        original = "[General]\nName=Crimson\n# my own profile\n"
        mine.write_text(original)
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "apply", "--yes", "--force")
        self.assertNotIn("# my own profile", mine.read_text())
        backups = sorted((self.s.home / ".local/state/crimson-desktop/backups/terminal-os").iterdir())
        theme_backup = [b for b in backups if b.name.endswith("konsole-theme")][-1]
        for _ in range(2):                           # restoring twice gives the same result
            self.s.sh("bash", str(SCRIPTS / "restore.sh"), str(theme_backup), "--yes")
            self.assertEqual(mine.read_text(), original)
            self.assertFalse((self.kdir / "Crimson OS.profile").exists())      # was absent before
            self.assertFalse((self.kdir / "Crimson.colorscheme").exists())

    def test_theme_remove_only_removes_unmodified_files(self):
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "apply", "--yes")
        scheme = self.kdir / "Crimson.colorscheme"
        with scheme.open("a") as f:
            f.write("# tweaked by me\n")
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "remove", "--yes")
        self.assertTrue(scheme.exists())
        self.assertFalse((self.kdir / "Crimson OS.profile").exists())
        self.assertFalse((self.kdir / "Crimson.profile").exists())

    def test_theme_remove_turns_autostart_off_first(self):
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "apply", "--yes")
        self.s.konsolerc.write_text(KONSOLERC_ORIG)
        self.s.sh("sh", str(BIN / "crimson-autostart"), "on")
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "remove", "--yes")
        self.assertEqual(self.s.konsolerc.read_text(), KONSOLERC_ORIG)

    def test_restore_without_backups_fails_cleanly(self):
        r = self.s.sh("bash", str(SCRIPTS / "restore.sh"), "--yes", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no backup found", r.stderr)

    def test_restore_asks_and_defaults_to_no(self):
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "apply", "--yes")
        r = subprocess.run(["bash", str(SCRIPTS / "restore.sh")], env=self.s.env(), input="\n",
                           capture_output=True, text=True, timeout=30)
        self.assertNotEqual(r.returncode, 0)   # no tty → default answer "no" → nothing changed
        self.assertTrue((self.kdir / "Crimson OS.profile").exists())

    def test_autostart_wrapper_script_accepts_yes(self):
        self.s.sh("bash", str(SCRIPTS / "konsole-theme.sh"), "apply", "--yes")
        self.s.sh("bash", str(SCRIPTS / "autostart.sh"), "on", "--yes")
        self.assertIn("DefaultProfile=Crimson OS.profile", self.s.konsolerc.read_text())
        self.s.sh("bash", str(SCRIPTS / "autostart.sh"), "off", "--yes")
        self.assertNotIn("DefaultProfile", self.s.konsolerc.read_text())


@unittest.skipUnless((TOS / ".venv" / "bin" / "python").exists(), "needs scripts/install.sh to have created terminal-os/.venv")
class EndToEndTests(unittest.TestCase):
    """The real TUI, started by the real wrapper in a pty under a fake `konsole` parent."""

    def setUp(self):
        self.s = Sandbox()
        self.addCleanup(self.s.cleanup)

    def session(self):
        import fcntl
        import struct
        import termios
        env = self.s.env(SHELL="/bin/bash", COLORTERM="truecolor", CRIMSON_TOS_LAUNCHER=str(BIN / "crimson"))
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(str(self.s.bin / "konsole"), [str(self.s.bin / "konsole"), str(BIN / "crimson-konsole")], env)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
        buf = bytearray()

        def pump(seconds, until=None):
            end = time.time() + seconds
            while time.time() < end:
                if until and until in buf:
                    return
                if select.select([fd], [], [], 0.1)[0]:
                    try:
                        buf.extend(os.read(fd, 65536))
                    except OSError:
                        return
        self.addCleanup(lambda: (os.close(fd), os.waitpid(pid, 0)))
        return fd, buf, pump

    def test_starts_quits_to_shell_and_subshell_round_trip(self):
        fd, buf, pump = self.session()
        pump(15, until=b"QUICK ACTIONS")
        self.assertIn(b"CRIMSON", buf)
        self.assertIn(b"\x1b[?1049h", buf)                 # alternate screen = full-screen TUI
        os.write(fd, b"\x13")                              # Ctrl+S: open a shell inside Crimson OS
        pump(3)
        os.write(fd, b"echo SUB-$((6*7))-$CRIMSON_TOS_SUBSHELL\n")
        pump(3, until=b"SUB-42-1")
        self.assertIn(b"SUB-42-1", buf)
        os.write(fd, b"exit\n")                            # back into the TUI
        pump(3)
        os.write(fd, b"\x11")                              # Ctrl+Q: leave Crimson OS
        pump(4)
        os.write(fd, b"echo SHELL-$((6*7))-[$CRIMSON_TOS_ACTIVE]\n")
        pump(3, until=b"SHELL-42-[]")
        self.assertIn(b"SHELL-42-[]", buf)                  # normal shell, guard variable cleared
        os.write(fd, b"exit\n")
        pump(1)


if __name__ == "__main__":
    unittest.main()
