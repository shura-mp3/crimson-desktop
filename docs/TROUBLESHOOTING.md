# Troubleshooting

Start with `crimsonctl doctor`, then `crimsonctl logs -f`.

**Dashboard appears on the wrong monitor.** Run `crimsonctl monitors` to see what was detected,
then set `monitor = "DP-2"` (your connector) under `[dashboard]` in
`~/.config/crimson-desktop/config.toml` and run `crimsonctl restart`.

**Dashboard is a normal window, or shows in the task bar.** Layer-shell isn't available. Check
`crimsonctl doctor` → "layer-shell". Fixes: `sudo dnf install layer-shell-qt`, and use Fedora's
`python3-pyside6` rather than pip's PySide6 (the pip build has its own Qt, which can't load KDE's
QML module). In window mode, the KWin rule from `apply-theme.sh` keeps the window below others,
borderless and out of the task bar. Re-run `apply-theme.sh` after changing monitors so the rule's
geometry is updated.

**"AWAITING SIGNAL" although Spotify is open.** Run `busctl --user list | grep mpris`. You should
see `org.mpris.MediaPlayer2.spotify`. If Spotify runs under a different name, add it to
`[spotify] players`. Flatpak Spotify works the same way. `playerctl -l` lists players too.

**Lyrics are early or late.** Scroll on the lyrics panel, use `+`/`-` in `crimson-lyrics`, or run
`crimsonctl offset +100`. That's saved per track. For a constant shift on every song, set
`[lyrics] latency_ms`. Positive values show lyrics earlier.

**No lyrics for a song.** Add `Artist - Title.lrc` to `~/.config/crimson-desktop/lyrics/` (or
`~/Music/Lyrics`). Local files always win. Force a fresh online lookup with `crimsonctl reload-lyrics`
or `r` in the TUI. You can also contribute lyrics on lrclib.net.

**Spectrum flat or "NO INPUT".**
* Check that `cava` is installed and that PipeWire is running (`pactl info`).
* Check that something is actually playing; CAVA only runs during playback.
* With `source = "spotify"`, the Spotify stream must exist (`pw-dump | grep -i spotify`). Otherwise
  it falls back to system audio.
* If your CAVA build lacks PipeWire, the core retries with the PulseAudio input automatically.

**Kitty isn't transparent or blurred.** Blur needs KWin's *Blur* desktop effect enabled
(`apply-theme.sh` enables it). Opacity is `background_opacity` in
`~/.config/kitty/crimson-profile.conf` (the Performance profile sets it to 1.0).

**Shortcuts don't work.** They're registered at login, so log out and back in. Check System
Settings → Keyboard → Shortcuts → "Crimson…" for conflicts.

**Games stutter.** Switch to `crimsonctl profile performance` (Meta+Alt+P). If you use GameMode
(`gamemoderun %command%` in Steam), the dashboard already drops to low automatically. Set
`gamemode_action = "hide"` to hide it completely during games.

**Lyrics look blurry or soft.** Since the lyric-rendering update, the big lyrics are drawn sharp at
your monitor's real resolution. If they still look soft:
* run `git pull` then `crimsonctl restart` (the dashboard only reloads its QML on restart);
* run `crimsonctl display`: it lists every monitor's resolution and scale as KDE sees them, and what
  the dashboard renders at (logical size × scale = physical pixels). The physical size should equal
  the right monitor's native mode;
* check `[ui] lyrics_style` in `~/.config/crimson-desktop/config.toml`: `"crisp"` is the default,
  `"retro"` is the deliberately chunky look. An old `pixelate_lyrics` line there is ignored now;
* measure the dashboard's cost on your GPU: `bin/crimson-dashboard --demo --stats 10` (opens a
  temporary preview window and prints fps and CPU time).

**Fonts look generic.** The dashboard loads its bundled fonts directly. For other apps, `install.sh`
copies them to `~/.local/share/fonts/crimson-desktop`. Run `fc-cache -f` if needed.

**Run things by hand:**
```bash
bin/crimson-core -v                        # backend with debug logging
bin/crimson-dashboard -v --mode window     # dashboard as a plain window
bin/crimson-dashboard --demo --mode window # preview with synthetic data (no Spotify needed)
```
