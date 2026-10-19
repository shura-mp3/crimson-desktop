# Backup & rollback

## What gets backed up

Every `scripts/apply-theme.sh` run first creates `backups/<YYYYMMDD-HHMMSS>-theme/` containing:

* `files.tar.gz`: every relevant file that existed, with permissions, timestamps, xattrs and ACLs.
  Covers `kdeglobals`, `kwinrc`, `kwinrulesrc`, `breezerc`, `plasmarc`, the Plasma desktop
  layout (`plasma-org.kde.plasma.desktop-appletsrc`), `plasmashellrc`, `kscreenlockerrc`,
  `kcminputrc`, `kglobalshortcutsrc`, `ksplashrc`, your whole `~/.config/kitty/`, and the
  Crimson files in `~/.config/cava`, `~/.config/fastfetch` and `~/.local/share`.
* `manifest.json`: which of those paths existed (restored) and which didn't (deleted on restore),
  plus your previous colour scheme, icon theme, cursor, Plasma style and accent colour, so they can
  be properly re-applied (restoring files alone wouldn't repaint running apps).
* `actions.log`: every single setting changed, with timestamps.

The **first** backup taken since the last restore is marked as your *original desktop*.

## Restore

```bash
scripts/restore-theme.sh            # back to your original, pre-Crimson desktop
scripts/restore-theme.sh --latest   # undo only the most recent apply-theme run
scripts/restore-theme.sh --list     # show backups; pass a name to restore that one
scripts/restore-theme.sh --keep-dashboard   # restore the theme but leave the dashboard running
```

Restore does the following:
1. Stops and disables the dashboard.
2. Stops plasmashell, so it can't overwrite its config mid-restore.
3. Deletes only the listed paths that didn't exist before.
4. Extracts the archive.
5. Re-applies your previous colour scheme, Plasma style, icons and cursor.
6. Restarts plasmashell and reconfigures KWin.

It is idempotent: running it again leaves the same result. This was verified in a sandbox,
including a double apply followed by a restore. Files came back byte-for-byte identical, with
the same permissions and timestamps.

Profile side effects (Performance turns animations and blur off) are reversible on their own: the
previous values are stored in `~/.local/state/crimson-desktop/profile-saved.json` and restored when
you switch back to another profile.

## Spotify (Spicetify) integration

Separate backups live in `backups/spicetify/`; restore them with `crimsonctl spotify restore`.
See [SPOTIFY.md](SPOTIFY.md).

## Removing the dashboard itself

```bash
scripts/uninstall.sh
```
This removes the systemd user units, the `~/.local/bin` links and the bundled fonts. It keeps your
config, cache and backups.

## Not undone automatically

* **Packages** installed by `install.sh` with your approval. They're listed in
  `~/.local/state/crimson-desktop/install-manifest.txt`, and `uninstall.sh` prints the exact
  `sudo dnf remove …` line. Removing shared packages automatically could break other software.
* **Font cache and desktop database refreshes** are harmless and regenerate themselves.
* **Lyrics and album-art caches** live in `~/.cache/crimson-desktop`. Delete that folder any time.
* KDE Plasma itself is never modified, replaced or removed. Your login screen and bootloader are
  not touched.
