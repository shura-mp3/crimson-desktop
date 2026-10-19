# Crimson Spotify (Spicetify integration)

Crimson Spotify themes the native Spotify client with [Spicetify](https://github.com/spicetify/cli) so that
it matches Crimson Desktop, and connects it to the **existing** crimson-core backend. Spotify, the
right-monitor dashboard and `crimson-lyrics` share one source of lyrics, offsets and audio spectrum.

## What you get

| | What it is | Where it comes from |
|---|---|---|
| **Crimson theme** | Crimson Night palette across all of Spotify; hairline-framed panels; clear hover, selected and playing rows; pixel-type album/playlist titles; crimson playback bar; Space Mono timestamps; styled menus, dialogs and scrollbars | this repo, `spicetify/theme/Crimson` |
| **Crimson page** (sidebar) | synced lyrics in line, karaoke or single-word mode; per-track offset buttons; real CAVA spectrum; now-playing info | this repo, `spicetify/apps/crimson` |
| **Full App Display** | full-window immersive now-playing: large art, title/artist/album, release date, progress, controls (styled by the theme) | built into Spicetify (`fullAppDisplay.js`, LGPL-2.1) |
| **Live profiles** | Minimal Dark, Performance, GameMode and the low performance level strip the theme's glow, scanlines and transitions **without restarting Spotify** | `theme.js` ↔ crimson-core |

Full source, license and selection notes for each component are in [`spicetify/manifest.json`](../spicetify/manifest.json).

## Commands

```bash
crimsonctl spotify inspect    # read-only report → spicetify/docs/INSPECTION.md (run this first)
crimsonctl spotify install    # backup → install → apply → verify   (safe to run again)
crimsonctl spotify status     # theme, extensions, bridge connection, health
crimsonctl spotify verify     # exit 1 if anything differs from the expected state
crimsonctl spotify doctor     # inspect + status + hints
crimsonctl spotify update     # after `git pull`: copies changed theme/app files, re-applies only if needed
crimsonctl spotify disable    # back to your previous Spicetify theme/extensions (Spicetify stays)
crimsonctl spotify enable     # turn Crimson back on
crimsonctl spotify restore    # restore the configuration from before Crimson Spotify was first installed
crimsonctl spotify restore --latest            # undo only the most recent install run
crimsonctl spotify restore --remove-spicetify  # also remove Spicetify, if Crimson Desktop installed it
```
If you have several Spotify installations, `install` won't guess which one to use; pass
`--target flatpak-system|flatpak-user|rpm|<path>`.

## How install works (and when it asks you)

1. **Inspect** (read-only): finds Spotify (Flatpak system/user, RPM, snap, and Spicetify's standard
   paths), its version, whether Spotify's files are writable and whether they are stock or already
   patched. It also checks Spicetify, its config and themes, and the project's git state. From
   Spotify's prefs it reads only `app.last-launched-version`; credentials and caches are never touched.
2. **Spicetify:** if it isn't installed, downloads the latest official release tarball into
   `~/.spicetify` and verifies the sha256 when GitHub publishes one. The official `install.sh` is
   **not** run, because it pipes a second remote script into `sh`. An existing Spicetify is never
   upgraded automatically.
3. **Permissions — asks first.** System-wide Spotify (system Flatpak or RPM) is owned by root. Spicetify's
   documented fix is `sudo chmod a+wr <spotify>` and `sudo chmod a+wr -R <spotify>/Apps`. You'll see the
   exact commands and the risk (any local user could modify Spotify's UI files) and must answer **y**.
   The original permissions are recorded so restore can offer to put them back. A per-user Flatpak
   needs no sudo; switching to one is your decision and is never done for you.
4. **Backup:** `backups/spicetify/<timestamp>-spicetify/` holds your Spicetify config, themes, extensions
   and apps, plus a `manifest.json` (previous theme, extensions, apps, Spotify state). It is verified
   before anything changes. The first backup is marked as your *original*.
5. **Install:** copies the theme and app (refusing to overwrite a `Crimson` folder it didn't create) and
   sets `current_theme`, `color_scheme`, `inject_theme_js`, `extensions += fullAppDisplay.js` and
   `custom_apps += crimson`. Your other extensions stay.
6. **Apply:** `spicetify backup apply` the first time, `spicetify apply` afterwards. This restarts
   Spotify, so it asks first if Spotify is playing.
7. **Verify:** checks the config, compares installed files with the project, checks Spotify's patched files, and
   waits for Spotify's Crimson script to connect to crimson-core. That last check proves the theme
   is actually running inside Spotify.

## How Spotify talks to Crimson Desktop

```
Spotify ── theme.js ──ws://127.0.0.1:47811──▶ crimson-core ◀── MPRIS/D-Bus ── Spotify
            (Crimson page uses it)               │  lyrics: local .lrc → cache → LRCLIB, offsets, CAVA
                                                 ├──▶ dashboard (unix socket)
                                                 └──▶ crimson-lyrics (unix socket)
```

* **One backend.** Nothing in Spotify looks up lyrics; it receives exactly what the dashboard and TUI
  show, including your per-track offsets. Changing the offset in any of the three applies to all of them.
* **One controller.** Spotify's own buttons and the Crimson page control Spotify directly. The dashboard
  and TUI control it through MPRIS. It's the same player either way, so they never compete. The bridge
  refuses playback commands.
* **Timing.** The Crimson page uses Spotify's own playback position, which is more precise than MPRIS.
  The dashboard and TUI use MPRIS. Both apply the same offsets.
* **Security.** The bridge is loopback-only and accepts only Spotify's UI origin
  (`https://xpui.app.spotify.com`), so web pages in your browser are refused (HTTP 403). It only
  allows subscribing and offset nudges (clamped to ±2000 ms) and never exposes system stats. Turn it
  off with `[spicetify] bridge = false`.
* **Resilience.** Without crimson-core, Spotify works normally and the Crimson page shows "CORE OFFLINE".
  `theme.js` retries with backoff (2 s up to 60 s).

## Theme reference

| role | colour | color.ini keys |
|---|---|---|
| background | `#0B080D` | main |
| surfaces | `#120B12` / `#190D16` | main-elevated, player / card |
| deep burgundy | `#230B17` | highlight, tab-active |
| crimson | `#8D2445` | button-secondary, nav-active, notification |
| rose (bars) | `#C0485F` | playback-bar |
| dusty pink | `#D58B9F` | button, accent, play-button, selected-row |
| pale pink | `#F2B7C5` | button-active, accent-active |
| text / subtext | `#F4E8ED` / `#A88B98` | text / subtext |
| borders | `#482033` | border-inactive, button-disabled, misc |

These are the same values as the KDE color scheme and the dashboard. Contrast was checked against
WCAG: body text is 16.7:1, secondary text 6.5:1, and every control pair is at least AA.

Typography: Spotify's own font for everything you read. **Jersey 10** (pixel) only for big
album/playlist/now-playing titles, Silkscreen for small labels and Space Mono for times. These are the
fonts `install.sh` puts in `~/.local/share/fonts`, which Flatpak apps can also see.

To customize, edit `spicetify/theme/Crimson/*`, then run `crimsonctl spotify update`.

## Limitations (honest list)

* **Spotify updates remove the theme.** That's how Spicetify works: each update replaces the patched
  files. Run `crimsonctl spotify install` again afterwards (`doctor` tells you when). If a new Spotify
  version isn't supported yet, Spotify still works un-themed; update Spicetify with `spicetify upgrade`
  when a release supports it.
* **System Flatpak and RPM installs need the one-time `sudo chmod`** (asks first), and Flatpak updates
  may reset it.
* **Spotify's internal class names change.** Colors come from `color.ini` variables, which are robust.
  The finer `user.css` structure uses the selectors maintained themes rely on, but a Spotify redesign
  can make some of those rules stop matching. The worst case is a plainer look, never a broken client.
* **Visualizer:** the Crimson page's bars are real CAVA output from PipeWire. They show *system* audio
  by default, or Spotify only with `[audio] source = "spotify"` (experimental). Spicetify itself has no
  access to Spotify's audio.
* **Lyrics:** coverage depends on LRCLIB and your `.lrc` files. Word highlighting appears only when the
  LRC really has word timestamps. Spotify's own lyrics endpoints are never used.
* **Startup:** nothing starts Spotify for you or moves it to a particular monitor.

## What was and wasn't tested

These were tested in the development environment (a cloud container without Spotify):
* **Bridge, against the real crimson-core:**
  * Spotify's origin is accepted; other origins and a missing origin are refused with 403.
  * Playback commands are ignored, offsets are clamped, and the `sys` topic is filtered out.
  * Garbage input doesn't drop the connection.
  * The real CAVA spectrum streams through it.
* **`theme.js` and the Crimson page in headless Chromium** (real React, mocked `Spicetify.Player`, real
  WebSocket to the real core):
  * word mode, line mode and the offset buttons;
  * live switch to the Performance profile with no reload;
  * "CORE OFFLINE" fallback when the core stops;
  * no JS errors.
* **The full `crimsonctl spotify` lifecycle with a Spicetify test double** that models the real CLI (its
  config list rules, backup/apply/restore and stock/applied detection):
  * *existing Sleek setup:* install → status → reinstall (idempotent) → update with no change → update
    after an edit → disable (Sleek back) → enable → restore. The config came back byte-identical, the
    user's theme and extension were untouched, and only Crimson-owned files were removed.
  * *stock per-user Flatpak:* install → restore. The original Spotify file came back byte-identical.
* **Static checks:** `user.css` parses (css-tree, 53 rules), every `--spice-*` variable is defined, the
  JS syntax is valid, and contrast ratios were computed.

**Not tested:** the real Spotify client and the real Spicetify binary on your machine. The things
only a real run can confirm:
* `user.css` selectors against your Spotify version;
* Full App Display behavior;
* the sudo-permission path;
* Flatpak sandbox access to the loopback port and to the fonts.

`crimsonctl spotify install` ends with `verify`, which reports the bridge connection from inside
Spotify, the most important of these.
