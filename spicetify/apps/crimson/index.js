// Crimson — Spicetify custom app (sidebar page) for Crimson Desktop.
//
// Lyrics, timing offsets and the audio spectrum come from crimson-core through the theme's
// shared bridge (window.CrimsonBridge) — the same local .lrc / cache / LRCLIB pipeline the
// desktop dashboard and crimson-lyrics use, so nothing is looked up twice.
// Playback position comes from Spotify itself (Spicetify.Player.getProgress), which is more
// precise than MPRIS. Controls use Spicetify.Player: one player, one controller.
// Word highlighting is only shown when the LRC really has word timestamps.

const react = Spicetify.React;
const { useState, useEffect, useRef, useCallback } = react;
const h = react.createElement;

const C = {
	bg: "#0B080D", panel: "#190D16", burgundy: "#230B17", crimson: "#8D2445", rose: "#C0485F",
	dusty: "#D58B9F", pale: "#F2B7C5", text: "#F4E8ED", muted: "#A88B98", border: "#482033",
};
const PIXEL = '"Jersey 10", "Pixelify Sans", "VT323", monospace';
const LABEL = '"Silkscreen", "Space Mono", monospace';
const MONO = '"Space Mono", "JetBrains Mono", monospace';

const STYLE = `
.crimson-app { min-height: 100%; padding: 24px 32px 40px; color: ${C.text}; box-sizing: border-box;
  background: repeating-linear-gradient(to bottom, transparent 0 3px, rgba(0,0,0,.16) 3px 4px), ${C.bg}; }
.crimson-reduce-effects .crimson-app { background: ${C.bg}; }
.crimson-panel { position: relative; background: rgba(25,13,22,.88); border: 1px solid ${C.border}; padding: 16px 20px; }
.crimson-panel::before, .crimson-panel::after { content: ""; position: absolute; width: 10px; height: 10px; border-color: ${C.dusty}; border-style: solid; }
.crimson-panel::before { top: -1px; left: -1px; border-width: 1px 0 0 1px; }
.crimson-panel::after { bottom: -1px; right: -1px; border-width: 0 1px 1px 0; }
.crimson-label { font-family: ${LABEL}; font-size: 10px; letter-spacing: .08em; color: ${C.muted}; text-transform: uppercase; }
.crimson-btn { font-family: ${LABEL}; font-size: 10px; letter-spacing: .06em; color: ${C.pale}; background: rgba(141,36,69,.25);
  border: 1px solid ${C.border}; padding: 6px 10px; cursor: pointer; transition: background-color 120ms, border-color 120ms; }
.crimson-btn:hover { background: ${C.crimson}; border-color: ${C.dusty}; }
.crimson-btn:focus-visible { outline: 2px solid ${C.dusty}; outline-offset: 2px; }
.crimson-line-current { font-family: ${PIXEL}; color: ${C.pale}; line-height: 1.02; text-shadow: 0 0 24px rgba(192,72,95,.55); transition: opacity 220ms, transform 220ms; }
.crimson-reduce-effects .crimson-line-current { text-shadow: none; }
.crimson-line-dim { font-family: ${PIXEL}; color: ${C.muted}; opacity: .5; }
`;

function trackId(x) {
	// "/com/spotify/track/ID" (MPRIS) or "spotify:track:ID" (Spotify) -> "ID"
	if (!x) return "";
	const parts = String(x).split(/[/:]/);
	return parts[parts.length - 1];
}
function lineIndex(lines, t) {
	let lo = 0, hi = lines.length - 1, ans = -1;
	while (lo <= hi) {
		const mid = (lo + hi) >> 1;
		if (lines[mid].t <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
	}
	return ans;
}
function wordIndex(line, t) {
	if (!line || !line.w) return -1;
	let n = -1;
	for (let i = 0; i < line.w.length; i++) if (line.w[i][0] <= t) n = i;
	return n;
}
function fmt(ms) {
	const s = Math.max(0, Math.floor(ms / 1000));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function spotifyTrack() {
	const item = Spicetify.Player.data?.item;
	if (!item) return null;
	const md = item.metadata || {};
	return {
		uri: item.uri,
		title: item.name || md.title || "",
		artist: (item.artists || []).map((a) => a.name).join(", ") || md.artist_name || "",
		album: item.album?.name || md.album_title || "",
		art: md.image_xlarge_url || md.image_large_url || md.image_url || item.album?.images?.[0]?.url || "",
		duration: Spicetify.Player.getDuration ? Spicetify.Player.getDuration() : item.duration?.milliseconds || 0,
	};
}

function useBridge() {
	const bridge = window.CrimsonBridge;
	const [state, setState] = useState(() => ({ ...(bridge?.state || {}) }));
	useEffect(() => {
		if (!bridge) return;
		const update = () => setState({ ...bridge.state });
		const events = ["status", "player", "lyrics", "ui"];
		events.forEach((e) => bridge.addEventListener(e, update));
		return () => events.forEach((e) => bridge.removeEventListener(e, update));
	}, [bridge]);
	return [bridge, state];
}

function Spectrum({ bridge }) {
	const canvas = useRef(null);
	const [live, setLive] = useState(false);
	useEffect(() => {
		if (!bridge) return;
		let frame = null, pending = null;
		const draw = () => {
			frame = null;
			const c = canvas.current;
			if (!c || !pending) return;
			const ctx = c.getContext("2d");
			const w = (c.width = c.clientWidth * devicePixelRatio), hgt = (c.height = c.clientHeight * devicePixelRatio);
			ctx.clearRect(0, 0, w, hgt);
			const n = pending.length, bw = w / n;
			for (let i = 0; i < n; i++) {
				const v = pending[i] / 255;
				const bh = Math.max(2, v * hgt * 0.95);
				const g = ctx.createLinearGradient(0, hgt - bh, 0, hgt);
				g.addColorStop(0, v > 0.6 ? C.pale : C.dusty);
				g.addColorStop(1, "rgba(141,36,69,0.5)");
				ctx.fillStyle = g;
				ctx.fillRect(i * bw + bw * 0.18, hgt - bh, bw * 0.64, bh);
			}
		};
		const onSpec = (e) => {
			pending = e.detail.b;
			setLive((was) => was || pending.some((v) => v > 0));
			if (!frame) frame = requestAnimationFrame(draw);
		};
		bridge.addEventListener("spec", onSpec);
		bridge.want("spec"); // CAVA runs in crimson-core only while someone wants it AND music plays
		const onVis = () => (document.hidden ? bridge.unwant("spec") : bridge.want("spec"));
		document.addEventListener("visibilitychange", onVis);
		return () => {
			bridge.removeEventListener("spec", onSpec);
			document.removeEventListener("visibilitychange", onVis);
			if (!document.hidden) bridge.unwant("spec");
			if (frame) cancelAnimationFrame(frame);
		};
	}, [bridge]);
	return h("div", { className: "crimson-panel", style: { height: 120, marginTop: 16 } },
		h("div", { className: "crimson-label", style: { position: "absolute", top: 8, left: 14 } },
			live ? "05 // SPECTRUM  ·  CAVA (SYSTEM AUDIO)" : "05 // SPECTRUM  ·  WAITING FOR AUDIO"),
		h("canvas", { ref: canvas, style: { width: "100%", height: "100%", display: "block" } }));
}

function Lyrics({ lyrics, matched, connected, track, position, wordMode }) {
	const status = lyrics?.status;
	const big = (text, sub) => h("div", { style: { textAlign: "center", padding: "48px 0" } },
		h("div", { className: "crimson-line-current", style: { fontSize: 72 } }, text),
		sub && h("div", { className: "crimson-label", style: { marginTop: 12 } }, sub));

	if (!connected) return big("CORE OFFLINE", "start the backend:  crimsonctl start   ·   Spotify keeps working without it");
	if (!track) return big("AWAITING SIGNAL", "press play");
	if (!matched || status === "loading") return big("SEARCHING…", "local .lrc → cache → lrclib.net");
	if (status === "instrumental") return big("♪ INSTRUMENTAL ♪", track.artist.toUpperCase());
	if (status === "ad") return big("ADVERTISEMENT");
	if (status === "error")
		return big("LYRICS UNREACHABLE", `${(lyrics.error || "network error").slice(0, 90)}  ·  ` +
			(lyrics.retry_in ? `retrying in ${lyrics.retry_in}s` : "gave up for this track — run: crimsonctl reload-lyrics"));
	if (status === "plain") return big((track.title || "").toUpperCase(), "UNSYNCED LYRICS ONLY — open crimson-lyrics to read them (no fake timing)");
	if (status !== "synced" || !lyrics.lines?.length) return big((track.title || "").toUpperCase(), "NO SYNCED LYRICS FOUND  ·  add an .lrc to ~/.config/crimson-desktop/lyrics/");

	const lines = lyrics.lines;
	const t = position + (lyrics.offset_ms || 0);
	const idx = lineIndex(lines, t);
	const cur = idx >= 0 ? lines[idx] : null;
	const wi = wordIndex(cur, t);
	const text = (i) => (i >= 0 && i < lines.length ? lines[i].text || "♪" : "");

	let current;
	if (!cur) {
		current = h("span", { style: { color: C.dusty } }, "· · ·");
	} else if (wordMode && cur.w) {
		current = h("span", null, (cur.w[Math.max(0, wi)][1] || "").trim().toUpperCase());
	} else if (cur.w) {
		current = cur.w.map((w, i) => h("span", { key: i, style: { color: i <= wi ? C.pale : "#8f5f6f" } }, w[1]));
	} else {
		current = text(idx);
	}
	return h("div", { style: { textAlign: "center", padding: "24px 0" } },
		h("div", { className: "crimson-line-dim", style: { fontSize: 26, minHeight: 32 } }, text(idx - 1)),
		h("div", { key: wordMode ? `w${idx}-${wi}` : `l${idx}`, className: "crimson-line-current",
			style: { fontSize: wordMode && cur?.w ? 128 : 64, margin: "14px 0", minHeight: 80 } }, current),
		wordMode && cur?.w && h("div", { style: { fontFamily: PIXEL, fontSize: 28, marginBottom: 8 } },
			cur.w.map((w, i) => h("span", { key: i, style: { color: i <= wi ? C.pale : "#8f5f6f" } }, w[1]))),
		h("div", { className: "crimson-line-dim", style: { fontSize: 32, color: C.dusty, opacity: 0.8 } }, text(idx + 1)),
		h("div", { className: "crimson-line-dim", style: { fontSize: 24 } }, text(idx + 2)));
}

function CrimsonApp() {
	const [bridge, bstate] = useBridge();
	const [track, setTrack] = useState(spotifyTrack);
	const [position, setPosition] = useState(() => Spicetify.Player.getProgress());
	const [playing, setPlaying] = useState(() => Spicetify.Player.isPlaying());
	const [wordMode, setWordMode] = useState(() => Spicetify.LocalStorage.get("crimson:word-mode") !== "0");

	useEffect(() => {
		const onSong = () => { setTrack(spotifyTrack()); setPosition(Spicetify.Player.getProgress()); };
		const onPlay = () => { setPlaying(Spicetify.Player.isPlaying()); setPosition(Spicetify.Player.getProgress()); };
		Spicetify.Player.addEventListener("songchange", onSong);
		Spicetify.Player.addEventListener("onplaypause", onPlay);
		return () => {
			Spicetify.Player.removeEventListener("songchange", onSong);
			Spicetify.Player.removeEventListener("onplaypause", onPlay);
		};
	}, []);
	useEffect(() => {
		// lyric clock: 20 Hz only while this page is open and music plays
		if (!playing) return;
		const id = setInterval(() => !document.hidden && setPosition(Spicetify.Player.getProgress()), 50);
		return () => clearInterval(id);
	}, [playing]);

	const toggleMode = useCallback(() => {
		setWordMode((m) => { Spicetify.LocalStorage.set("crimson:word-mode", m ? "0" : "1"); return !m; });
	}, []);

	const lyrics = bstate.lyrics;
	const coreTrack = bstate.player?.track;
	const matched = !!(track && lyrics && (trackId(lyrics.track_id) === trackId(track.uri) ||
		(coreTrack && coreTrack.title === track.title && trackId(coreTrack.id) === trackId(lyrics.track_id))));
	const hasWords = !!lyrics?.has_words;
	const ui = bstate.ui || {};

	return h("div", { className: "crimson-app" },
		h("style", null, STYLE),
		h("div", { className: "crimson-panel", style: { display: "flex", gap: 20, alignItems: "center" } },
			track?.art && h("img", { src: track.art, alt: "", style: { width: 112, height: 112, objectFit: "cover", border: `1px solid ${C.border}` } }),
			h("div", { style: { flex: 1, minWidth: 0 } },
				h("div", { className: "crimson-label" },
					`01 // NOW PLAYING  ·  ${playing ? "LIVE" : "HOLD"}  ·  CORE ${bstate.connected ? "LINKED" : "OFFLINE"}` +
					(ui.profile ? `  ·  PROFILE ${String(ui.profile).toUpperCase()}` : "")),
				h("div", { style: { fontFamily: PIXEL, fontSize: 48, color: C.pale, lineHeight: 1.15, margin: "4px 0", paddingBottom: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" } },
					track?.title || "—"),
				h("div", { style: { fontFamily: MONO, fontWeight: 700, color: C.dusty } }, track?.artist || ""),
				h("div", { style: { fontFamily: MONO, fontSize: 12, color: C.muted } },
					(track?.album || "") + (track ? `  ·  ${fmt(position)} / ${fmt(track.duration)}` : ""))),
			h("div", { style: { display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-end" } },
				h("div", { className: "crimson-label" },
					lyrics?.status === "synced" ? `${hasWords ? "WORD" : "LINE"} SYNC · ${(lyrics.source || "").toUpperCase()}` : (lyrics?.status || "").toUpperCase()),
				h("div", { className: "crimson-label" }, `OFFSET ${(lyrics?.offset_ms || 0) >= 0 ? "+" : ""}${lyrics?.offset_ms || 0} MS`),
				h("div", { style: { display: "flex", gap: 6 } },
					h("button", { className: "crimson-btn", title: "lyrics later (-100 ms)", disabled: !bstate.connected, onClick: () => bridge.offset(-100) }, "−100"),
					h("button", { className: "crimson-btn", title: "reset offset for this track", disabled: !bstate.connected, onClick: () => bridge.offset("reset") }, "0"),
					h("button", { className: "crimson-btn", title: "lyrics earlier (+100 ms)", disabled: !bstate.connected, onClick: () => bridge.offset(100) }, "+100")),
				hasWords && h("button", { className: "crimson-btn", onClick: toggleMode }, wordMode ? "LINE MODE" : "WORD MODE"))),
		h("div", { className: "crimson-panel", style: { marginTop: 16 } },
			h("div", { className: "crimson-label" }, "04 // LYRICS.SYS"),
			h(Lyrics, { lyrics, matched, connected: bstate.connected, track, position, wordMode: wordMode && hasWords })),
		bstate.connected && h(Spectrum, { bridge }));
}

function render() {
	if (!window.CrimsonBridge) {
		return h("div", { style: { padding: 40, color: C.pale, fontFamily: MONO } },
			"The Crimson theme script is not active. Run: crimsonctl spotify install  (it sets inject_theme_js = 1).");
	}
	return h(CrimsonApp);
}
