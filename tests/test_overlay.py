import json
import urllib.request

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


def test_page_state_and_frame(overlay):
    e = Engine(make_cfg(meter={"min_votes": 1}), overlay)
    e.handle(msg("red", "up"), 0)
    overlay.update(e.overlay_state(0))

    status, headers, body = get(overlay, "/")
    assert status == 200 and b"<canvas" in body and "text/html" in headers["Content-Type"]

    state = json.loads(get(overlay, "/state")[2])
    assert state["mode"] == "anarchy" and state["inputs"] == ["red  up"]
    assert state["threshold"] == 0.8 and state["share"] == 0.0

    assert get(overlay, "/frame")[0] == 204  # no game frame yet
    overlay.set_frame(160, 144, bytes(160 * 144 * 4))
    status, headers, body = get(overlay, "/frame")
    assert status == 200 and headers["X-Width"] == "160" and len(body) == 160 * 144 * 4


def test_state_in_democracy_and_ai_modes():
    e = Engine(make_cfg(meter={"min_votes": 1, "start_mode": "democracy"}))
    e.handle(msg("a", "up2"), 0)
    s = e.overlay_state(5)
    assert s["votes"] == [["up2", 1]] or s["votes"] == [("up2", 1)]
    assert s["seconds_left"] == 15
    json.dumps(s)  # must be JSON-ready

    ai = Engine(make_cfg(ai={"enabled": True}))
    ai.apply_ai("heading to the gym", ["up"])
    s = ai.overlay_state(0)
    assert s["mode"] == "ai" and s["summary"] == "heading to the gym"


def test_busy_port_gives_a_clear_error(overlay):
    with pytest.raises(SystemExit, match=r"\[overlay\].port"):
        Overlay(port=overlay.port).start()
