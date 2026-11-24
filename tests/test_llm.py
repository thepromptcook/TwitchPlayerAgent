import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from conftest import gta_cfg, make_cfg, msg
from twitchplayeragent.backends import LogBackend
from twitchplayeragent.config import Config
from twitchplayeragent.engine import Engine
from twitchplayeragent.llm import Planner, format_chat, unavailable
from twitchplayeragent.modes import Mode


class FakeClient:
    """Stands in for anthropic.AsyncAnthropic: records calls, returns canned answers."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        block = SimpleNamespace(type="tool_use", name="press_buttons", input=answer)
        return SimpleNamespace(stop_reason="tool_use", content=[block])


def ai_cfg(**ai):
    return make_cfg(ai={"enabled": True, **ai})


def test_the_ai_only_knows_the_games_commands():
    pokemon = Planner(Config())
    assert pokemon.schema["properties"]["presses"]["items"]["enum"] == ["a", "b", "down", "left", "right", "start", "up"]
    assert pokemon.tool["strict"] is True and pokemon.tool["input_schema"] is pokemon.schema
    gta = Planner(gta_cfg())
    assert set(gta.schema["properties"]["presses"]["items"]["enum"]) == set(gta.cfg.game.commands)
    assert "- drive: accelerate on/off" in gta.system and "Grand Theft Auto VI" in gta.system
    cfg = ai_cfg()
    cfg.game.name, cfg.game.ai_notes = "Tetris", "Left and right move the piece."
    prompt = Planner(cfg).system
    assert "Tetris" in prompt and "Left and right move the piece." in prompt
    assert "Pok" not in prompt  # no Pokémon text hardcoded in the core


def test_format_chat_collapses_repeats():
    text = format_chat([msg("a", "up"), msg("b", "UP"), msg("c", "go into the grass"), msg("d", "up ")])
    assert text == "<chat>\n3x up\nc: go into the grass\n</chat>"


def test_planner_filters_and_caps_presses():
    client = FakeClient({"summary": "walk up", "presses": ["up", "select", "up", "up", "up"]})
    p = Planner(ai_cfg(max_presses=3), client)
    p.add(msg("ash", "go up"))
    assert asyncio.run(p.decide()) == ("walk up", ["up", "up", "up"])  # select isn't allowed; capped
    assert "go up" in client.calls[0]["messages"][0]["content"]
    assert client.calls[0]["model"] == "claude-haiku-5-5"


def test_planner_skips_quiet_windows_and_survives_errors():
    p = Planner(ai_cfg(), FakeClient(RuntimeError("network down")))
    assert asyncio.run(p.decide()) is None  # no chat: no call
    p.add(msg("ash", "a"))
    assert asyncio.run(p.decide()) is None  # the error is logged, not raised
    assert p.buffer == []


def test_previous_summary_is_passed_on():
    client = FakeClient({"summary": "heading to the gym", "presses": ["up"]},
                        {"summary": "still going", "presses": []})
    p = Planner(ai_cfg(), client)
    p.add(msg("a", "gym"))
    asyncio.run(p.decide())
    p.add(msg("b", "keep going"))
    asyncio.run(p.decide())
    assert "heading to the gym" in client.calls[1]["messages"][0]["content"]


def test_engine_in_ai_mode():
    e = Engine(ai_cfg())
    assert e.mode is Mode.AI
    e.handle(msg("v", "democracy"), 0)  # mode votes go to the AI like any chat
    e.handle(msg("v", "up"), 0)
    assert e.next_press() is None  # nothing pressed until the AI decides
    assert [m.text for m in e.planner.buffer] == ["democracy", "up"]
    e.apply_ai("go up", ["up", "up"])
    e.apply_ai("actually left", ["left"])  # a new decision replaces the old one
    assert [e.next_press(), e.next_press()] == ["left", None]


def test_run_end_to_end():
    e = Engine(ai_cfg(window_seconds=0.1))
    e.planner.client = FakeClient({"summary": "open the menu", "presses": ["start", "a"]})

    async def chat():
        yield msg("ash", "open the menu please")

    backend = LogBackend(delay=0)
    asyncio.run(asyncio.wait_for(e.run(chat(), backend), timeout=5))
    assert backend.pressed == ["start", "a"]  # the replay waited for the AI's answer


@pytest.fixture
def fake_ollama():
    """A tiny stand-in for Ollama's HTTP API on a random localhost port."""
    state = {"models": ["qwen3.5:27b"], "reply": {"summary": "go up", "presses": ["up", "up"]}, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # /api/tags
            self._send({"models": [{"name": n} for n in state["models"]]})

        def do_POST(self):  # /api/chat
            state["requests"].append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self._send({"message": {"role": "assistant", "content": json.dumps(state["reply"])}})

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()


def test_ollama_decides_with_the_schema(fake_ollama):
    p = Planner(ai_cfg(provider="ollama", ollama_url=fake_ollama["url"]))
    p.add(msg("ash", "walk up a bit"))
    assert asyncio.run(p.decide()) == ("go up", ["up", "up"])
    sent = fake_ollama["requests"][0]
    assert sent["model"] == "qwen3.5:27b" and sent["format"] == p.schema
    assert sent["think"] is False and sent["stream"] is False
    assert "walk up a bit" in sent["messages"][1]["content"] and "JSON" in sent["messages"][0]["content"]
    fake_ollama["reply"] = "not an object"  # a bad answer is skipped
    p.add(msg("ash", "up"))
    assert asyncio.run(p.decide()) is None


def test_ollama_startup_checks(fake_ollama):
    cfg = ai_cfg(provider="ollama", ollama_url=fake_ollama["url"])
    assert unavailable(cfg) == ""
    cfg.ai.model = "llama9:70b"
    assert "ollama pull llama9:70b" in unavailable(cfg)
    assert unavailable(cfg, check_server=False) == ""  # !mode ai never waits on the network
    cfg.ai.ollama_url = "http://127.0.0.1:9"  # nothing listening
    assert "isn't reachable" in unavailable(cfg)
