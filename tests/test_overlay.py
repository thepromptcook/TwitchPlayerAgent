import json
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from conftest import make_cfg, msg
from twitchplayeragent.engine import Engine
from twitchplayeragent.overlay import Overlay


@pytest.fixture
def overlay():
    o = Overlay(port=0)  # any free port
    o.start()
    yield o
    o.stop()


def get(o, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{o.port}{path}", timeout=5) as r:
        return r.status, dict(r.headers), r.read()


def test_page_and_state(overlay):
    e = Engine(make_cfg(meter={"min_votes": 1}), overlay)
    e.handle(msg("red", "up"), 0)
    overlay.update(e.overlay_state(0))

    status, headers, body = get(overlay, "/")
    assert status == 200 and b"<canvas" in body and "text/html" in headers["Content-Type"]
    assert b"const AUDIO = true;" in body
    state = json.loads(get(overlay, "/state")[2])
    assert state["mode"] == "anarchy" and state["inputs"] == ["red  up"]
    assert state["threshold"] == 0.8 and state["share"] == 0.0
    assert get(overlay, "/favicon.ico")[0] == 204


def test_state_in_democracy_and_ai_modes():
    e = Engine(make_cfg(meter={"min_votes": 1, "start_mode": "democracy"}))
    e.handle(msg("a", "up2"), 0)
    s = json.loads(json.dumps(e.overlay_state(5)))  # must be JSON-ready
    assert s["votes"] == [["up2", 1]] and s["seconds_left"] == 15

    ai = Engine(make_cfg(ai={"enabled": True}))
    ai.apply_ai("heading to the gym", ["up"])
    s = ai.overlay_state(0)
    assert s["mode"] == "ai" and s["summary"] == "heading to the gym"


def test_frame_stream_pushes_every_frame(overlay):
    def feed():
        for i in range(30):
            overlay.set_frame(2, 1, bytes([i]) * 8)
            time.sleep(0.01)

    s = socket.create_connection(("127.0.0.1", overlay.port), timeout=5)
    s.sendall(b"GET /frames HTTP/1.0\r\n\r\n")
    threading.Thread(target=feed, daemon=True).start()
    header, data = struct.pack("<HH", 2, 1), b""
    while data.count(header) < 20 and len(data) < 10_000:
        data += s.recv(4096)
    s.close()
    body = data.split(b"\r\n\r\n", 1)[1]
    values = [body[i + 4] for i in range(0, len(body) - 11, 12) if body[i:i + 4] == header]
    assert len(values) >= 19 and values == sorted(values)  # in order, none merged


def test_audio_endpoint_streams_new_samples(overlay):
    assert get(overlay, "/audio")[2] == b""  # nothing yet
    for i in range(10):
        overlay.add_audio(48000, bytes([i]) * 4)
    _, headers, body = get(overlay, "/audio")  # a new listener gets only the latest 3 chunks
    assert headers["X-Seq"] == "10" and headers["X-Rate"] == "48000"
    assert body == bytes([7]) * 4 + bytes([8]) * 4 + bytes([9]) * 4
    overlay.add_audio(48000, b"\x0a\x0a")
    assert get(overlay, "/audio?after=10")[2] == b"\x0a\x0a"  # just what's new


def test_audio_can_be_off():
    o = Overlay(port=0, audio=False)
    o.start()
    try:
        assert b"const AUDIO = false;" in get(o, "/")[2]
    finally:
        o.stop()


def test_busy_port_gives_a_clear_error(overlay):
    with pytest.raises(SystemExit, match=r"\[overlay\].port"):
        Overlay(port=overlay.port).start()


def test_page_script_is_valid_javascript(tmp_path):
    """A JS syntax error blanks the whole overlay, and Python tests can't see it.
    Checked with Node.js when it's installed."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js not installed")
    html = (Path(__file__).parent.parent / "twitchplayeragent" / "overlay.html").read_text(encoding="utf-8")
    script = tmp_path / "page.js"
    script.write_text(html[html.index("<script>") + 8:html.index("</script>")], encoding="utf-8")
    result = subprocess.run([node, "--check", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
