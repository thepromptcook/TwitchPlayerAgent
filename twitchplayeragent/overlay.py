"""Stream overlay as one local web page, for a single OBS Browser Source.

http://localhost:<[overlay].port>/ (default 8080) shows the game screen plus the
input list, anarchy/democracy meter, democracy votes and AI summary, laid out
for a 1920x1080 canvas. The game image comes straight from the emulator's
memory, so it keeps working when the game window is minimized or behind other
windows. Open the same URL in a normal browser to preview it.

Endpoints: /  (the page)  /state  (JSON, polled 4x a second)  /frame  (raw RGBA
pixels of the latest game frame; 204 when there's none, e.g. keyboard backend).
Only 127.0.0.1 is served. Chat text is inserted with textContent, never as HTML.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)


class Overlay:
    def __init__(self, port: int = 8080) -> None:
        self.port = port
        self.state: dict = {}
        self.frame: tuple[int, int, bytes] | None = None  # width, height, RGBA bytes
        self._server: ThreadingHTTPServer | None = None

    def update(self, state: dict) -> None:
        self.state = state  # replaced whole, so readers never see a half update

    def set_frame(self, width: int, height: int, rgba: bytes) -> None:
        self.frame = (width, height, rgba)

    def start(self) -> None:
        overlay = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                if path == "/":
                    self._send(200, "text/html; charset=utf-8", PAGE.encode())
                elif path == "/state":
                    self._send(200, "application/json", json.dumps(overlay.state).encode())
                elif path == "/frame" and overlay.frame is not None:
                    w, h, data = overlay.frame
                    self._send(200, "application/octet-stream", data, {"X-Width": w, "X-Height": h})
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
            self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
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


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>TwitchPlayerAgent overlay</title>
<style>
  html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: transparent;
    font: 28px/1.3 Consolas, "Courier New", monospace; color: #f2f2f2; }
  #game { position: absolute; left: 0; top: 0; width: 1200px; height: 1080px; background: #000;
    image-rendering: pixelated; display: none; }
  #panel { position: absolute; left: 1200px; top: 0; width: 720px; height: 1080px; box-sizing: border-box;
    padding: 28px 32px; background: #15151c; display: flex; flex-direction: column; gap: 22px; }
  #mode { font-size: 52px; font-weight: bold; letter-spacing: 3px; }
  .anarchy { color: #ff5a5a; } .democracy { color: #5aa0ff; } .ai { color: #c58bff; }
  #meter { position: relative; height: 34px; background: #ff5a5a; border-radius: 4px; overflow: hidden; }
  #meter .dem { position: absolute; right: 0; top: 0; bottom: 0; background: #5aa0ff; }
  #meter .mark { position: absolute; top: 0; bottom: 0; width: 4px; background: #fff; }
  #meter-labels { display: flex; justify-content: space-between; font-size: 20px; color: #aaa; margin-top: 6px; }
  #info { color: #ddd; white-space: pre-wrap; }
  #info .row { display: flex; justify-content: space-between; }
  #inputs { flex: 1; overflow: hidden; display: flex; flex-direction: column; justify-content: flex-end; }
  #inputs div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #inputs .user { color: #9a9aa8; }
  #inputs .sys { color: #ffd166; }
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
  const mode = $("mode"); mode.textContent = s.mode.toUpperCase(); mode.className = s.mode;
  $("meterbox").style.display = s.mode === "ai" ? "none" : "";
  $("meter").querySelector(".dem").style.width = (s.share * 100) + "%";
  $("meter").querySelector(".mark").style.right = (s.threshold * 100) + "%";
  const info = $("info"); info.replaceChildren();
  if (s.mode === "ai") info.append(el("div", "", s.summary || "Waiting for chat"));
  if (s.mode === "democracy") {
    info.append(el("div", "", s.seconds_left == null ? "Waiting for votes"
                                : "Next input in " + Math.ceil(s.seconds_left) + "s"));
    for (const [key, n] of s.votes.slice(0, 5)) {
      const row = el("div", "row"); row.append(el("span", "", key),
        el("span", "", n + "  " + Math.round(100 * n / Math.max(1, s.total_votes)) + "%"));
      info.append(row);
    }
  }
  const list = $("inputs"); list.replaceChildren();
  for (const line of s.inputs) {
    const sys = line.startsWith(">>") || line.startsWith("***");
    const [user, ...rest] = line.split("  ");
    const row = el("div", sys ? "sys" : "");
    if (sys || !rest.length) row.textContent = line;
    else row.append(el("span", "user", user + "  "), el("span", "", rest.join("  ")));
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
pollState(); pollFrames();
</script></body></html>
"""
