"""Stream overlay: one local web page for a single OBS Browser Source.

http://localhost:<[overlay].port>/ (default 8080) shows the game plus mode, meter,
votes or AI summary, and recent inputs on a 1920x1080 canvas: a thin bar under the
game by default, or the original stream's sidebar with /?layout=sidebar. Picture
and sound come straight from the emulator, so the game window can be minimized.
The page itself is overlay.html (edit it there; tests syntax-check its script).

Routes (127.0.0.1 only):
  /              the page
  /state         JSON from Engine.overlay_state, polled 4x a second
  /frames        one long response pushing every frame as it's drawn:
                 <HH width,height header + width*height RGBA bytes
  /audio?after=N signed 8-bit stereo samples newer than chunk N (X-Seq, X-Rate headers)
"""

from __future__ import annotations

import json
import logging
import struct
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger(__name__)

PAGE = Path(__file__).with_name("overlay.html").read_text(encoding="utf-8")


class Overlay:
    def __init__(self, port: int = 8080, audio: bool = True) -> None:
        self.port = port
        self.page = PAGE if audio else PAGE.replace("const AUDIO = true;", "const AUDIO = false;", 1)
        self.state: dict = {}
        self.frame: tuple[int, int, bytes] | None = None  # width, height, RGBA bytes
        self._frame_seq = 0
        self._frame_ready = threading.Condition()
        self.audio_rate = 0
        self._audio: deque[tuple[int, bytes]] = deque(maxlen=300)  # (seq, chunk), ~5 s at 60/s
        self._audio_seq = 0
        self._audio_lock = threading.Lock()
        self._server: _Server | None = None

    # ---- fed by the engine and the backend --------------------------------

    def update(self, state: dict) -> None:
        self.state = state  # replaced whole, so readers never see a half update

    def set_frame(self, width: int, height: int, rgba: bytes) -> None:
        with self._frame_ready:
            self.frame = (width, height, rgba)
            self._frame_seq += 1
            self._frame_ready.notify_all()  # wake every /frames stream

    def add_audio(self, rate: int, samples: bytes) -> None:
        """One emulated frame of sound: interleaved stereo, signed 8-bit."""
        if samples:
            with self._audio_lock:
                self.audio_rate = rate
                self._audio_seq += 1
                self._audio.append((self._audio_seq, samples))

    # ---- read by the HTTP handler ------------------------------------------

    def next_frame(self, after: int, timeout: float = 1.0) -> tuple[int, tuple[int, int, bytes] | None]:
        """Wait for a frame newer than ``after``: (seq, frame), or (after, None) on timeout."""
        with self._frame_ready:
            if not self._frame_ready.wait_for(lambda: self._frame_seq != after, timeout):
                return after, None
            return self._frame_seq, self.frame

    def audio_since(self, after: int) -> tuple[int, bytes]:
        """(latest seq, samples newer than ``after``). A new listener (after < 0) or one
        that fell behind gets only the last 3 chunks, to stay near live."""
        with self._audio_lock:
            chunks, latest = list(self._audio), self._audio_seq
        if after < 0 or (chunks and after < chunks[0][0] - 1):
            after = latest - 3
        return latest, b"".join(data for seq, data in chunks if seq > after)

    # ---- server ----------------------------------------------------------------

    def start(self) -> None:
        try:
            self._server = _Server(("127.0.0.1", self.port), _Handler)
        except OSError as exc:
            raise SystemExit(
                f"Overlay can't use port {self.port} ({exc.strerror}). "
                "Close whatever uses it or set [overlay].port to another number."
            ) from None
        self._server.overlay = self
        self.port = self._server.server_address[1]  # the real port when 0 was asked for
        threading.Thread(target=self._server.serve_forever, name="overlay", daemon=True).start()
        log.info("Overlay at http://localhost:%d  (OBS: Browser Source, 1920x1080)", self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None


class _Server(ThreadingHTTPServer):
    # Python's HTTP server sets SO_REUSEADDR. On Mac/Linux that only skips the TIME_WAIT
    # wait after a restart; on Windows it lets a second program bind a port that's in
    # use instead of failing, so two bots could silently share 8080. Off on Windows.
    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True
    overlay: Overlay


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def do_GET(self) -> None:
        overlay = self.server.overlay
        url = urlsplit(self.path)
        if url.path == "/":
            self._send(200, "text/html; charset=utf-8", overlay.page.encode())
        elif url.path == "/state":
            self._send(200, "application/json", json.dumps(overlay.state).encode())
        elif url.path == "/frames":
            self._stream_frames(overlay)
        elif url.path == "/audio":
            after = int(parse_qs(url.query).get("after", ["-1"])[0])
            seq, data = overlay.audio_since(after)
            self._send(200, "application/octet-stream", data, {"X-Seq": seq, "X-Rate": overlay.audio_rate})
        elif url.path == "/favicon.ico":
            self._send(204, "text/plain", b"")
        else:
            self._send(404, "text/plain", b"not found")

    def _stream_frames(self, overlay: Overlay) -> None:
        # One long HTTP/1.0 response (it ends when the connection closes), so each frame
        # arrives the moment it's drawn. Polling one request per frame managed ~30 fps.
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        seq = -1
        while overlay._server is not None:
            seq, frame = overlay.next_frame(seq)
            if frame is not None:
                w, h, data = frame
                try:
                    self.wfile.write(struct.pack("<HH", w, h) + data)
                    self.wfile.flush()
                except OSError:  # page closed or reloaded
                    return

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
