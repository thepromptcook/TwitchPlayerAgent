import asyncio

from conftest import drain, make_cfg, msg
from twitchplayeragent.backends import LogBackend
from twitchplayeragent.engine import Engine
from twitchplayeragent.modes import Mode


def make(**meter):
    return Engine(make_cfg(meter={"min_votes": 1, **meter}))


def test_anarchy_executes_everything_in_order():
    e = make()
    for u, t in [("a", "up"), ("b", "A"), ("c", "hello"), ("d", "up2"), ("e", "start")]:
        e.handle(msg(u, t), 0)
    assert drain(e) == ["up", "a", "start"]


def test_anarchy_queue_is_bounded():
    e = Engine(make_cfg(anarchy={"max_queue": 3}))
    for i, b in enumerate(["up", "down", "left", "right"]):
        e.handle(msg(str(i), b), 0)
    assert drain(e) == ["down", "left", "right"]


def test_democracy_round():
    e = make(start_mode="democracy")
    e.cfg.democracy.window_seconds = 20
    e.handle(msg("a", "up2"), 0)
    e.handle(msg("b", "upup"), 1)
    e.handle(msg("c", "start9"), 2)
    e.tick(10)
    assert drain(e) == []  # round still open
    e.tick(20)
    assert drain(e) == ["up", "up"]
    assert e.round_ends_at is None


def test_democracy_wait_wins_presses_nothing():
    e = make(start_mode="democracy")
    e.handle(msg("a", "wait"), 0)
    e.handle(msg("b", "wait"), 0)
    e.handle(msg("c", "a"), 0)
    e.tick(100)
    assert drain(e) == []


def test_switching_modes_clears_pending_inputs():
    e = make()
    e.handle(msg("a", "up"), 0)
    e.handle(msg("v", "democracy"), 0)
    assert e.mode is Mode.DEMOCRACY
    assert drain(e) == []
    e.handle(msg("x", "left"), 1)
    e.handle(msg("v", "anarchy"), 2)
    assert e.mode is Mode.ANARCHY
    e.tick(100)
    assert drain(e) == []


def test_run_end_to_end_with_log_backend():
    async def chat():
        for t in ["up", "a", "nope", "b"]:
            yield msg("u", t)

    e = make()
    backend = LogBackend(delay=0)
    asyncio.run(asyncio.wait_for(e.run(chat(), backend), timeout=5))
    assert backend.pressed == ["up", "a", "b"]


def test_example_chat_replays():
    """examples/chat.txt stays valid: only its exact commands press buttons."""
    from pathlib import Path

    e = make()
    for line in Path(__file__).parent.parent.joinpath("examples/chat.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            user, _, text = line.partition(":")
            e.handle(msg(user.strip(), text.strip()), 0)
    assert drain(e) == ["start", "a", "a", "a", "down", "down", "right", "b", "left"]


def test_a_controller_game_queues_its_commands():
    from twitchplayeragent.config import load_config

    e = Engine(load_config(["config.example.toml", "games/gta6.toml"]))
    for user, text in [("a", "goup"), ("b", "steal that car"), ("c", "enter"), ("d", "up2"),
                       ("e", "drive"), ("f", "left"), ("g", "start")]:
        e.handle(msg(user, text), 0)
    assert drain(e) == ["goup", "enter", "drive", "left"]  # up2/start aren't anarchy commands


def test_ticker_changes_from_chat_and_survives_a_restart(tmp_path):
    from twitchplayeragent.chat import ChatMessage

    saved = tmp_path / "ticker.txt"
    cfg = make_cfg(overlay={"ticker": "Welcome!", "ticker_file": str(saved)})
    e = Engine(cfg)
    assert e.overlay_state(0)["ticker"] == "Welcome!"  # config default until changed
    e.handle(ChatMessage("troll", "troll", "!ticker free robux"), 0)  # viewers can't
    assert e.ticker == "Welcome!"
    e.handle(ChatMessage("me", "Me", "!TICKER   Back in   5 minutes ", mod=True), 0)
    assert e.ticker == "Back in 5 minutes" and drain(e) == []  # never a game command
    assert Engine(cfg).ticker == "Back in 5 minutes"  # a restart keeps the latest
    e.handle(ChatMessage("me", "Me", "!ticker", mod=True), 0)  # clear
    assert Engine(cfg).ticker == ""  # stays cleared, even with a config default


def test_streamer_can_force_the_mode():
    from twitchplayeragent.chat import ChatMessage

    e = make(min_votes=3)
    for user in ("a", "b", "c"):
        e.handle(msg(user, "anarchy"), 0)  # three live anarchy votes
    e.handle(ChatMessage("viewer", "viewer", "!mode democracy"), 0)  # viewers can't
    assert e.mode is Mode.ANARCHY
    e.handle(msg("x", "up"), 0)
    e.handle(ChatMessage("me", "Me", "!MODE Democracy", mod=True), 1)
    assert e.mode is Mode.DEMOCRACY and drain(e) == []  # switched; anarchy queue cleared
    e.tick(2)
    assert e.mode is Mode.DEMOCRACY  # the old anarchy votes were forgotten
    e.handle(ChatMessage("me", "Me", "!mode chaos", mod=True), 3)  # unknown: ignored
    assert e.mode is Mode.DEMOCRACY
    e.handle(ChatMessage("me", "Me", "!mode anarchy", mod=True), 4)
    assert e.mode is Mode.ANARCHY


def test_mode_ai_switches_in_and_out(monkeypatch):
    from twitchplayeragent.chat import ChatMessage

    me = lambda text: ChatMessage("me", "Me", text, mod=True)  # noqa: E731
    monkeypatch.setattr("twitchplayeragent.engine.unavailable", lambda cfg, check_server: "no API key")
    e = make()
    e.handle(me("!mode ai"), 0)
    assert e.mode is Mode.ANARCHY  # not set up: stays put (and logs why)

    monkeypatch.setattr("twitchplayeragent.engine.unavailable", lambda cfg, check_server: "")
    e.handle(msg("a", "up"), 0)
    e.handle(me("!mode ai"), 1)
    assert e.mode is Mode.AI and drain(e) == []  # the anarchy queue is cleared
    e.handle(msg("b", "go to the pokemon center"), 2)
    assert [m.text for m in e.planner.buffer] == ["go to the pokemon center"]  # chat goes to the AI
    e.handle(me("!mode democracy"), 3)
    assert e.mode is Mode.DEMOCRACY and e.planner.buffer == []
    e.handle(msg("c", "up2"), 3)
    assert e.tally.total == 1  # back to voting
