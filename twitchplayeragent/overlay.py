"""Stream overlay as one local web page, for a single OBS Browser Source.

http://localhost:<[overlay].port>/ (default 8080) shows the game screen plus the
input list, anarchy/democracy meter, democracy votes and AI summary, laid out
for a 1920x1080 canvas: a thin bar under the game by default, or the original
stream's right-hand sidebar with /?layout=sidebar. The game image comes straight from the emulator's
memory, so it keeps working when the game window is minimized or behind other
windows. Open the same URL in a normal browser to preview it.

Game sound goes through the page too (``[overlay].audio``), so the one Browser
Source carries picture and sound.

Endpoints: /  (the page)  /state  (JSON, polled 4x a second)  /frame  (raw RGBA
pixels of the latest game frame; 204 when there's none, e.g. keyboard backend)
/audio?after=N  (signed 8-bit stereo samples newer than chunk N, header X-Seq).

Only 127.0.0.1 is served. Chat text is inserted with textContent, never as HTML.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)


class Overlay:
    def __init__(self, port: int = 8080, audio: bool = True) -> None:
        self.port = port
        self.audio = audio
        self.state: dict = {}
        self.frame: tuple[int, int, bytes] | None = None  # width, height, RGBA bytes
        self.audio_rate = 0
        self._audio: deque[tuple[int, bytes]] = deque(maxlen=300)  # (seq, chunk), ~5 s at 60/s
        self._audio_seq = 0
        self._audio_lock = threading.Lock()
        self._server: _Server | None = None

    def update(self, state: dict) -> None:
        self.state = state  # replaced whole, so readers never see a half update

    def set_frame(self, width: int, height: int, rgba: bytes) -> None:
        self.frame = (width, height, rgba)

    def add_audio(self, rate: int, samples: bytes) -> None:
        """One emulated frame of sound: interleaved stereo, signed 8-bit."""
        if not samples:
            return
        with self._audio_lock:
            self.audio_rate = rate
            self._audio_seq += 1
            self._audio.append((self._audio_seq, samples))

    def audio_since(self, after: int) -> tuple[int, bytes]:
        """(latest seq, samples newer than ``after``). A new listener (after < 0)
        or one that fell behind gets only the last few chunks, to stay near live."""
        with self._audio_lock:
            chunks = list(self._audio)
            latest = self._audio_seq
        if after < 0 or (chunks and after < chunks[0][0] - 1):
            after = latest - 3
        return latest, b"".join(data for seq, data in chunks if seq > after)

    def start(self) -> None:
        overlay = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                if path == "/":
                    page = PAGE.replace("const $ =", f"const AUDIO = {str(overlay.audio).lower()};\nconst $ =", 1)
                    self._send(200, "text/html; charset=utf-8", page.encode())
                elif path == "/state":
                    self._send(200, "application/json", json.dumps(overlay.state).encode())
                elif path == "/frame" and overlay.frame is not None:
                    w, h, data = overlay.frame
                    self._send(200, "application/octet-stream", data, {"X-Width": w, "X-Height": h})
                elif path == "/audio":
                    query = self.path.partition("?")[2]
                    after = int(query.partition("after=")[2] or -1) if "after=" in query else -1
                    seq, data = overlay.audio_since(after)
                    self._send(200, "application/octet-stream", data,
                               {"X-Seq": seq, "X-Rate": overlay.audio_rate})
                elif path in ("/frame", "/favicon.ico"):
                    self._send(204, "text/plain", b"")
                else:
                    self._send(404, "text/plain", b"not found")

            def _send(self, code: int, ctype: str, body: bytes, extra: dict | None = None) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, str(v))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # no per-request logging
                pass

        try:
            self._server = _Server(("127.0.0.1", self.port), Handler)
        except OSError as exc:
            raise SystemExit(
                f"Overlay can't use port {self.port} ({exc.strerror}). "
                "Close whatever uses it or set [overlay].port to another number."
            ) from None
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]  # real port when 0 was asked for
        threading.Thread(target=self._server.serve_forever, name="overlay", daemon=True).start()
        log.info("Overlay at http://localhost:%d  (OBS: Browser Source, 1920x1080)", self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None


class _Server(ThreadingHTTPServer):
    """Refuses a port another program is listening on, on every OS. Python's HTTP
    server sets SO_REUSEADDR: harmless on Mac/Linux (it only skips the post-restart
    TIME_WAIT delay), but on Windows it lets a second program bind a port that's in
    use instead of failing, so it's off there. Windows has no TIME_WAIT delay to skip."""

    allow_reuse_address = sys.platform != "win32"


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>TwitchPlayerAgent overlay</title>
<style>
  html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: transparent;
    font: 28px/1.3 Consolas, "Courier New", monospace; color: #f2f2f2; }
  #game { position: absolute; background: #000; image-rendering: pixelated; display: none; }
  #panel { position: absolute; box-sizing: border-box; background: #15151c; display: flex; }
  #mode { font-weight: bold; }
  .anarchy { color: #ff5a5a; } .democracy { color: #5aa0ff; } .ai { color: #c58bff; }
  #meter { position: relative; background: #ff5a5a; border-radius: 4px; overflow: hidden; }
  #meter .dem { position: absolute; right: 0; top: 0; bottom: 0; background: #5aa0ff; }
  #meter .mark { position: absolute; top: 0; bottom: 0; width: 4px; background: #fff; }
  #meter-labels { display: flex; justify-content: space-between; font-size: 20px; color: #aaa; margin-top: 6px; }
  #info { color: #ddd; }
  #info .row { display: flex; justify-content: space-between; }
  #inputs { overflow: hidden; display: flex; }
  #inputs div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #inputs .user { color: #9a9aa8; }
  #inputs .sys { color: #ffd166; }

  /* Default: a thin bar under the game. The game is scaled exactly 7x (1120x1008) and
     the bar sits below it, never over it: Pokemon's text boxes are at the bottom. */
  .bar #game { left: 400px; top: 0; width: 1120px; height: 1008px; }
  .bar #panel { left: 0; top: 1008px; width: 1920px; height: 72px; padding: 0 28px;
    align-items: center; gap: 28px; font-size: 26px; }
  .bar #mode { font-size: 34px; letter-spacing: 2px; flex: none; }
  .bar #meterbox { width: 260px; flex: none; }
  .bar #meter { height: 22px; }
  .bar #meter-labels { display: none; }
  .bar #info { flex: none; max-width: 1100px; white-space: pre; overflow: hidden; text-overflow: ellipsis; }
  .bar #inputs { flex: 1; align-items: center; gap: 26px;
    -webkit-mask-image: linear-gradient(to right, #000 88%, transparent); }
  .bar #inputs div { flex: none; }

  /* ?layout=sidebar: the original stream's look, game left and a 720 px panel right. */
  .sidebar #game { left: 0; top: 0; width: 1200px; height: 1080px; }
  .sidebar #panel { left: 1200px; top: 0; width: 720px; height: 1080px; padding: 28px 32px;
    flex-direction: column; gap: 22px; }
  .sidebar #mode { font-size: 52px; letter-spacing: 3px; }
  .sidebar #meter { height: 34px; }
  .sidebar #info { white-space: pre-wrap; }
  .sidebar #inputs { flex: 1; flex-direction: column; justify-content: flex-end; }
</style></head><body>
<canvas id="game" width="160" height="144"></canvas>
<div id="panel">
  <div id="mode"></div>
  <div id="meterbox"><div id="meter"><div class="dem"></div><div class="mark"></div></div>
    <div id="meter-labels"><span>ANARCHY</span><span>DEMOCRACY</span></div></div>
  <div id="info"></div>
  <div id="inputs"></div>
</div>
<script>
const $ = id => document.getElementById(id);
document.body.className = new URLSearchParams(location.search).get("layout") === "sidebar" ? "sidebar" : "bar";
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text; return e; }

async function pollState() {
  try {
    const s = await (await fetch("/state", {cache: "no-store"})).json();
    if (s.mode) render(s);
  } catch (e) {}
  setTimeout(pollState, 250);
}

function render(s) {
  const bar = document.body.className === "bar";
  const mode = $("mode"); mode.textContent = s.mode.toUpperCase(); mode.className = s.mode;
  $("meterbox").style.display = s.mode === "ai" ? "none" : "";
  $("meter").querySelector(".dem").style.width = (s.share * 100) + "%";
  $("meter").querySelector(".mark").style.right = (s.threshold * 100) + "%";
  const info = $("info"); info.replaceChildren();
  const pct = n => Math.round(100 * n / Math.max(1, s.total_votes)) + "%";
  const countdown = s.seconds_left == null ? "Waiting for votes" : Math.ceil(s.seconds_left) + "s";
  if (s.mode === "ai") info.textContent = s.summary || "Waiting for chat";
  else if (s.mode === "democracy" && bar) {  // one line: "13s  up2left 55%  start9 32%"
    info.textContent = [countdown, ...s.votes.slice(0, 3).map(([k, n]) => k + " " + pct(n))].join(" · ");
  } else if (s.mode === "democracy") {
    info.append(el("div", "", s.seconds_left == null ? countdown : "Next input in " + countdown));
    for (const [key, n] of s.votes.slice(0, 5)) {
      const row = el("div", "row"); row.append(el("span", "", key), el("span", "", n + "  " + pct(n)));
      info.append(row);
    }
  }
  const list = $("inputs"); list.replaceChildren();
  // Bar: newest first, left to right; sidebar: oldest at the top, newest at the bottom.
  for (const line of bar ? [...s.inputs].reverse().slice(0, 12) : s.inputs) {
    const sys = line.startsWith(">>") || line.startsWith("***");
    const [user, ...rest] = line.split("  ");
    const row = el("div", sys ? "sys" : "");
    if (sys || !rest.length) row.textContent = line;
    else row.append(el("span", "user", user + " "), el("span", "", rest.join("  ")));
    list.append(row);
  }
}

async function pollFrames() {
  const canvas = $("game"), ctx = canvas.getContext("2d");
  let last = 0;
  for (;;) {
    await new Promise(r => requestAnimationFrame(r));
    const now = performance.now();
    if (now - last < 33) continue;  // ~30 fps is plenty for a Game Boy
    last = now;
    try {
      const r = await fetch("/frame", {cache: "no-store"});
      if (r.status !== 200) { canvas.style.display = "none"; continue; }
      const w = +r.headers.get("X-Width"), h = +r.headers.get("X-Height");
      const px = new Uint8ClampedArray(await r.arrayBuffer());
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      ctx.putImageData(new ImageData(px, w, h), 0, 0);
      canvas.style.display = "block";
    } catch (e) { canvas.style.display = "none"; }
  }
}
// Game sound: poll new samples and schedule them back to back with a small
// buffer. PyBoy's samples run 0..127 (never negative), so a DC blocker centres
// the wave; otherwise playback clicks. OBS allows autoplay; in a normal browser,
// click the page once to start sound.
async function pollAudio() {
  let ctx = null, seq = -1, next = 0;
  const dc = [{x: 0, y: 0}, {x: 0, y: 0}];
  addEventListener("click", () => ctx && ctx.resume());
  for (;;) {
    await new Promise(r => setTimeout(r, 40));
    try {
      const r = await fetch("/audio?after=" + seq, {cache: "no-store"});
      seq = +r.headers.get("X-Seq");
      const rate = +r.headers.get("X-Rate");
      const raw = new Int8Array(await r.arrayBuffer());
      if (!rate || raw.length < 2) continue;
      if (!ctx) { ctx = new AudioContext({sampleRate: rate}); ctx.resume(); }
      const frames = raw.length >> 1, buf = ctx.createBuffer(2, frames, rate);
      for (let c = 0; c < 2; c++) {
        const out = buf.getChannelData(c), f = dc[c];
        for (let i = 0; i < frames; i++) {
          const x = raw[2 * i + c] / 128;
          f.y = x - f.x + 0.995 * f.y; f.x = x; out[i] = f.y;
        }
      }
      const now = ctx.currentTime;
      if (next < now + 0.02 || next > now + 0.4) next = now + 0.12;  // (re)start or catch up
      const src = ctx.createBufferSource(); src.buffer = buf; src.connect(ctx.destination);
      src.start(next); next += buf.duration;
      window.audioFramesPlayed = (window.audioFramesPlayed || 0) + frames;
    } catch (e) {}
  }
}
pollState(); pollFrames(); if (AUDIO) pollAudio();
</script></body></html>
"""
