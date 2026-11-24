import asyncio
from types import SimpleNamespace

from twitchplayeragent.backends.log_backend import LogBackend
from twitchplayeragent.chat import ChatMessage
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


def msg(user, text):
    return ChatMessage(user, user, text)


def claude_cfg(**kw):
    cfg = Config()
    cfg.claude.enabled = True
    for k, v in kw.items():
        setattr(cfg.claude, k, v)
    return cfg


def test_tool_only_allows_real_buttons():
    tool = build_tool(Config().allowed_buttons)
    enum = tool["input_schema"]["properties"]["presses"]["items"]["enum"]
    assert enum == ["a", "b", "down", "left", "right", "start", "up"]
    assert tool["strict"] is True


def test_format_chat_collapses_repeats():
    text = format_chat([msg("a", "up"), msg("b", "UP"), msg("c", "go into the grass"), msg("d", "up ")])
    assert text == "<chat>\n3x up\nc: go into the grass\n</chat>"


def test_planner_filters_and_caps_presses():
    cfg = claude_cfg(max_presses=3)
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
    p = Planner(claude_cfg(), FakeClient(RuntimeError("network down")))
    assert asyncio.run(p.decide()) is None  # no chat: no call
    p.add(msg("ash", "a"))
    assert asyncio.run(p.decide()) is None  # error is logged, not raised
    assert p.buffer == []


def test_previous_summary_is_passed_on():
    client = FakeClient({"summary": "heading to the gym", "presses": ["up"]},
                        {"summary": "still going", "presses": []})
    p = Planner(claude_cfg(), client)
    p.add(msg("a", "gym"))
    asyncio.run(p.decide())
    p.add(msg("b", "keep going"))
    asyncio.run(p.decide())
    assert "heading to the gym" in client.calls[1]["messages"][0]["content"]


def test_engine_in_claude_mode():
    e = Engine(claude_cfg())
    assert e.mode is Mode.CLAUDE
    e.handle(msg("v", "democracy"), 0)  # mode votes go to Claude like any chat
    e.handle(msg("v", "up"), 0)
    assert e.next_press() is None  # nothing pressed until Claude decides
    assert [m.text for m in e.planner.buffer] == ["democracy", "up"]
    e.apply_claude("go up", ["up", "up"])
    e.apply_claude("actually left", ["left"])  # a new decision replaces the old one
    assert [e.next_press(), e.next_press()] == ["left", None]


def test_run_end_to_end():
    cfg = claude_cfg(window_seconds=0.1)
    e = Engine(cfg)
    e.planner.client = FakeClient({"summary": "open the menu", "presses": ["start", "a"]})

    async def chat():
        yield msg("ash", "open the menu please")

    backend = LogBackend(delay=0)
    asyncio.run(asyncio.wait_for(e.run(chat(), backend), timeout=5))
    assert backend.pressed == ["start", "a"]
