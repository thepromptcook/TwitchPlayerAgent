import asyncio
from types import SimpleNamespace

from conftest import make_cfg, msg
from twitchplayeragent.backends import LogBackend
from twitchplayeragent.config import Config
from twitchplayeragent.engine import Engine
from twitchplayeragent.llm import Planner, build_tool, format_chat
from twitchplayeragent.modes import Mode


class FakeClient:
    """Stands in for anthropic.AsyncAnthropic: records calls, returns canned answers."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []
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


def test_tool_only_allows_real_buttons():
    tool = build_tool(Config().allowed_buttons)
    enum = tool["input_schema"]["properties"]["presses"]["items"]["enum"]
    assert enum == ["a", "b", "down", "left", "right", "start", "up"]
    assert tool["strict"] is True


def test_format_chat_collapses_repeats():
    text = format_chat([msg("a", "up"), msg("b", "UP"), msg("c", "go into the grass"), msg("d", "up ")])
    assert text == "<chat>\n3x up\nc: go into the grass\n</chat>"


def test_planner_filters_and_caps_presses():
    cfg = ai_cfg(max_presses=3)
    client = FakeClient({"summary": "walk up", "presses": ["up", "select", "up", "up", "up"]})
    p = Planner(cfg, client)
    p.add(msg("ash", "go up"))
    summary, presses = asyncio.run(p.decide())
    assert summary == "walk up"
    assert presses == ["up", "up", "up"]  # select isn't allowed, capped at 3
    sent = client.calls[0]
    assert "go up" in sent["messages"][0]["content"]
    assert sent["model"] == "claude-haiku-5-5"


def test_planner_skips_quiet_windows_and_survives_errors():
    p = Planner(ai_cfg(), FakeClient(RuntimeError("network down")))
    assert asyncio.run(p.decide()) is None  # no chat: no call
    p.add(msg("ash", "a"))
    assert asyncio.run(p.decide()) is None  # error is logged, not raised
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
    assert e.next_press() is None  # nothing pressed until Claude decides
    assert [m.text for m in e.planner.buffer] == ["democracy", "up"]
    e.apply_ai("go up", ["up", "up"])
    e.apply_ai("actually left", ["left"])  # a new decision replaces the old one
    assert [e.next_press(), e.next_press()] == ["left", None]


def test_run_end_to_end():
    cfg = ai_cfg(window_seconds=0.1)
    e = Engine(cfg)
    e.planner.client = FakeClient({"summary": "open the menu", "presses": ["start", "a"]})

    async def chat():
        yield msg("ash", "open the menu please")

    backend = LogBackend(delay=0)
    asyncio.run(asyncio.wait_for(e.run(chat(), backend), timeout=5))
    assert backend.pressed == ["start", "a"]


# ---- Ollama (local) ---------------------------------------------------------------

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from twitchplayeragent.llm import unavailable


@pytest.fixture
def fake_ollama():
    """A tiny stand-in for Ollama's HTTP API on a random localhost port."""
    state = {"models": ["qwen3.5:27b"], "reply": {"summary": "go up", "presses": ["up", "up"]},
             "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body):
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # /api/tags
            self._send({"models": [{"name": n} for n in state["models"]]})

        def do_POST(self):  # /api/chat
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(body)
            self._send({"message": {"role": "assistant", "content": json.dumps(state["reply"])}})

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()


def test_ollama_decides_with_schema(fake_ollama):
    cfg = ai_cfg(provider="ollama", ollama_url=fake_ollama["url"])
    p = Planner(cfg)
    p.add(msg("ash", "walk up a bit"))
    assert asyncio.run(p.decide()) == ("go up", ["up", "up"])
    sent = fake_ollama["requests"][0]
    assert sent["model"] == "qwen3.5:27b"
    assert sent["format"]["properties"]["presses"]["items"]["enum"] == sorted(cfg.allowed_buttons)
    assert sent["think"] is False and sent["stream"] is False
    assert "walk up a bit" in sent["messages"][1]["content"]
    assert "JSON" in sent["messages"][0]["content"]


def test_ollama_bad_answer_is_skipped(fake_ollama):
    fake_ollama["reply"] = "not an object"
    p = Planner(ai_cfg(provider="ollama", ollama_url=fake_ollama["url"]))
    p.add(msg("ash", "up"))
    assert asyncio.run(p.decide()) is None


def test_ollama_startup_checks(fake_ollama):
    cfg = ai_cfg(provider="ollama", ollama_url=fake_ollama["url"])
    assert unavailable(cfg) == ""
    cfg.ai.model = "llama9:70b"
    assert "ollama pull llama9:70b" in unavailable(cfg)
    cfg.ai.ollama_url = "http://127.0.0.1:9"  # nothing listening
    assert "isn't reachable" in unavailable(cfg)


def test_game_knowledge_comes_from_config():
    from twitchplayeragent.llm import build_system

    cfg = ai_cfg()
    cfg.game.name, cfg.game.ai_notes = "Tetris", "Left and right move the piece."
    prompt = build_system(cfg)
    assert "Tetris" in prompt and "Left and right move the piece." in prompt
    assert "Pok" not in prompt  # no Pokémon text hardcoded in the core
