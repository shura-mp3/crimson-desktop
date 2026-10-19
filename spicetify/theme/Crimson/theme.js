// Crimson Spotify — theme script (injected by Spicetify when inject_theme_js = 1)
//
// 1. Opens ONE loopback WebSocket to crimson-core (ws://127.0.0.1:47811) and exposes it as
//    window.CrimsonBridge for the "Crimson" custom app. The core is the single source of
//    lyrics / offsets / spectrum shared with the desktop dashboard and crimson-lyrics.
// 2. Mirrors the desktop profile (Crimson Music / Minimal Dark / Performance, GameMode,
//    low performance level) onto <html> classes so user.css can reduce effects live.
// If crimson-core isn't running, Spotify is unaffected: the bridge just retries with backoff.

(function CrimsonTheme() {
	if (!window.Spicetify || !Spicetify.Player || !Spicetify.LocalStorage) {
		setTimeout(CrimsonTheme, 300);
		return;
	}
	if (window.CrimsonBridge) return;

	const PORT = parseInt(Spicetify.LocalStorage.get("crimson:bridge-port") || "47811", 10);
	const URL = `ws://127.0.0.1:${PORT}`;
	const PROFILE_CLASSES = ["crimson-profile-crimson", "crimson-profile-minimal", "crimson-profile-performance", "crimson-reduce-effects"];

	const bridge = new EventTarget();
	bridge.state = { connected: false, player: null, lyrics: null, ui: null };
	bridge.wanted = new Map(); // topic -> refcount (beyond the always-on ones)
	let ws = null;
	let backoff = 2000;

	bridge.send = (obj) => {
		if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
	};
	const pushTopics = () => bridge.send({ cmd: "sub", topics: [...bridge.wanted.keys()] });
	bridge.want = (topic) => {
		bridge.wanted.set(topic, (bridge.wanted.get(topic) || 0) + 1);
		pushTopics();
	};
	bridge.unwant = (topic) => {
		const n = (bridge.wanted.get(topic) || 1) - 1;
		if (n <= 0) bridge.wanted.delete(topic);
		else bridge.wanted.set(topic, n);
		pushTopics();
	};
	bridge.offset = (delta) => bridge.send(delta === "reset" ? { cmd: "offset", reset: true } : { cmd: "offset", delta });

	function applyProfile(ui) {
		const root = document.documentElement;
		root.classList.remove(...PROFILE_CLASSES);
		if (!ui) return;
		root.classList.add(`crimson-profile-${ui.profile || "crimson"}`);
		if (ui.profile !== "crimson" || ui.effective_performance === "low") root.classList.add("crimson-reduce-effects");
	}

	function connect() {
		try {
			ws = new WebSocket(URL);
		} catch (e) {
			return schedule();
		}
		ws.onopen = () => {
			backoff = 2000;
			bridge.state.connected = true;
			pushTopics();
			bridge.dispatchEvent(new CustomEvent("status", { detail: true }));
		};
		ws.onmessage = (ev) => {
			let msg;
			try {
				msg = JSON.parse(ev.data);
			} catch (e) {
				return;
			}
			const t = msg.t;
			if (t === "player" || t === "lyrics" || t === "ui") bridge.state[t] = msg;
			if (t === "ui") applyProfile(msg);
			bridge.dispatchEvent(new CustomEvent(t, { detail: msg }));
		};
		ws.onclose = () => {
			const was = bridge.state.connected;
			bridge.state.connected = false;
			if (was) bridge.dispatchEvent(new CustomEvent("status", { detail: false }));
			schedule();
		};
		ws.onerror = () => {}; // onclose follows
	}
	function schedule() {
		setTimeout(connect, backoff);
		backoff = Math.min(backoff * 2, 60000); // 2 s .. 60 s: negligible cost while core is off
	}

	window.CrimsonBridge = bridge;
	connect();
})();
