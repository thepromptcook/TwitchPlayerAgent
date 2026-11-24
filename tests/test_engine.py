from conftest import drain, make_cfg, msg
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


def test_democracy_rounds():
    e = make(start_mode="democracy")
    e.handle(msg("a", "up2"), 0)
    e.handle(msg("b", "upup"), 1)
    e.handle(msg("c", "start9"), 2)
    e.tick(10)
    assert drain(e) == []  # the round (20 s from its first vote) is still open
    e.tick(20)
    assert drain(e) == ["up", "up"] and e.round_ends_at is None
    for u, t in [("a", "wait"), ("b", "wait"), ("c", "a")]:
        e.handle(msg(u, t), 30)
    e.tick(100)
    assert drain(e) == []  # "wait" won: nothing pressed


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


def test_ticker_changes_from_chat_and_survives_a_restart(tmp_path):
    cfg = make_cfg(overlay={"ticker": "Welcome!", "ticker_file": str(tmp_path / "ticker.txt")})
    e = Engine(cfg)
    assert e.overlay_state(0)["ticker"] == "Welcome!"  # the config default until changed
    e.handle(msg("troll", "!ticker free robux"), 0)  # viewers can't
    assert e.ticker == "Welcome!"
    e.handle(msg("me", "!TICKER   Back in   5 minutes ", mod=True), 0)
    assert e.ticker == "Back in 5 minutes" and drain(e) == []  # never a game command
    assert Engine(cfg).ticker == "Back in 5 minutes"  # a restart keeps the latest
    e.handle(msg("me", "!ticker", mod=True), 0)  # clear
    assert Engine(cfg).ticker == ""  # stays cleared, even with a config default


def test_streamer_can_force_the_mode():
    e = make(min_votes=3)
    for user in ("a", "b", "c"):
        e.handle(msg(user, "anarchy"), 0)  # three live anarchy votes
    e.handle(msg("viewer", "!mode democracy"), 0)  # viewers can't
    assert e.mode is Mode.ANARCHY
    e.handle(msg("x", "up"), 0)
    e.handle(msg("me", "!MODE Democracy", mod=True), 1)
    assert e.mode is Mode.DEMOCRACY and drain(e) == []  # switched; the anarchy queue cleared
    e.tick(2)
    assert e.mode is Mode.DEMOCRACY  # the old anarchy votes were forgotten
    e.handle(msg("me", "!mode chaos", mod=True), 3)  # unknown: ignored
    assert e.mode is Mode.DEMOCRACY
    e.handle(msg("me", "!mode anarchy", mod=True), 4)
    assert e.mode is Mode.ANARCHY


def test_mode_ai_switches_in_and_out(monkeypatch):
    monkeypatch.setattr("twitchplayeragent.engine.unavailable", lambda cfg, check_server: "no API key")
    e = make()
    e.handle(msg("me", "!mode ai", mod=True), 0)
    assert e.mode is Mode.ANARCHY  # not set up: stays put (and logs why)
    monkeypatch.setattr("twitchplayeragent.engine.unavailable", lambda cfg, check_server: "")
    e.handle(msg("a", "up"), 0)
    e.handle(msg("me", "!mode ai", mod=True), 1)
    assert e.mode is Mode.AI and drain(e) == []  # the anarchy queue is cleared
    e.handle(msg("b", "go to the pokemon center"), 2)
    assert [m.text for m in e.planner.buffer] == ["go to the pokemon center"]  # chat goes to the AI
    e.handle(msg("me", "!mode democracy", mod=True), 3)
    assert e.mode is Mode.DEMOCRACY and e.planner.buffer == []
    e.handle(msg("c", "up2"), 3)
    assert e.tally.total == 1  # back to voting
