"""The command line, config loading, and the whole bot replaying chat offline."""

import io
import logging
import threading
from pathlib import Path

import pytest

from conftest import gta_cfg
from twitchplayeragent.__main__ import main, setup_logging, stop_on_ctrl_c
from twitchplayeragent.config import load_config


@pytest.mark.parametrize("game,chat,presses", [
    ([], Path("examples/chat.txt").read_text(encoding="utf-8"), "start a a a down down right b left"),
    (["games/gta6.toml"], "a: goup\nb: steal that car\nc: enter\nd: up2\ne: drive\nf: left\ng: start\n",
     "goup enter drive left"),  # up2 and start aren't anarchy commands in GTA
], ids=["pokemon", "gta6"])
def test_offline_replay(tmp_path, monkeypatch, caplog, game, chat, presses):
    """python -m twitchplayeragent -c config.example.toml [-c games/<game>.toml] --stdin --dry-run < chat"""
    quiet = tmp_path / "quiet.toml"
    quiet.write_text("[overlay]\nenabled = false\n")
    monkeypatch.setattr("sys.stdin", io.StringIO(chat))
    caplog.set_level(logging.INFO)
    main([arg for path in ["config.example.toml", *game, quiet] for arg in ("-c", str(path))] + ["--stdin", "--dry-run"])
    assert [r.getMessage()[6:] for r in caplog.records if r.getMessage().startswith("PRESS ")] == presses.split()


def test_ctrl_c_stops_gently_then_forces():
    stop = threading.Event()
    handler = stop_on_ctrl_c(stop)
    handler(2, None)  # the first Ctrl+C asks the game loop to save and quit
    assert stop.is_set()
    with pytest.raises(KeyboardInterrupt):  # the second forces it
        handler(2, None)


def test_log_lines_are_prefixed_once(capsys):
    root = logging.getLogger()
    saved, level = root.handlers[:], root.level
    root.handlers = []
    try:
        listener = setup_logging(False)
        logging.getLogger("twitchplayeragent.engine").info("PRESS up")
        listener.stop()
    finally:
        root.handlers, root.level = saved, level
    err = capsys.readouterr().err
    assert "twitchplayeragent.engine: PRESS up" in err and "INFO:" not in err


@pytest.mark.parametrize("text,error", [
    ("[twitch]\nchannel = yourname\n", "line 2:  channel = yourname\n  Hint: text values need quotes"),
    ("[twitch]\nchannel = “yourname”\n", "curly quotes"),
    ("[overlay]\ndir = \"overlay\"\n", r"unknown keys in \[overlay\]: \['dir'\]"),
    ("[game.commands]\njump = { button = \"A\" }\n", r"\[game.commands\] need \[backend\].type = 'gamepad'"),
    (None, "Can't read the config file"),
])
def test_config_mistakes_are_explained(tmp_path, text, error):
    path = tmp_path / "config.toml"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    with pytest.raises(SystemExit, match=error):
        load_config(path)


@pytest.mark.parametrize("command,error", [
    ('jump = { button = "Z" }', "button must be one of"),
    ('jump = { stick = "middle", y = 1 }', "stick must be"),
    ('jump = { stick = "left", y = 2 }', "between -1 and 1"),
    ('jump = { buton = "A" }', "unknown fields"),
    ('wait = { button = "A" }', "lowercase letters only"),
    ('jump = { seconds = 1 }', "needs a button"),
    ('jump = "A"', "write it as a table"),
])
def test_bad_game_commands_are_explained(tmp_path, command, error):
    game = tmp_path / "game.toml"
    game.write_text(f'[backend]\ntype = "gamepad"\n[game.commands]\n{command}\n')
    with pytest.raises(SystemExit, match=error):
        load_config(game)


def test_a_game_file_layers_on_the_main_config():
    cfg = gta_cfg()
    assert cfg.backend.type == "gamepad" and "goup" in cfg.allowed_commands
    assert cfg.twitch.channel == "your_channel_name"  # kept from the main config
    assert cfg.democracy.window_seconds == 5  # the game file wins where it says so
    assert cfg.meter.min_votes == 5
