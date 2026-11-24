"""Command-line helpers and config loading."""

import threading

import pytest

from twitchplayeragent.__main__ import stop_on_ctrl_c
from twitchplayeragent.config import load_config


def test_ctrl_c_stops_gently_then_forces():
    stop = threading.Event()
    handler = stop_on_ctrl_c(stop)
    handler(2, None)  # first Ctrl+C: ask the game loop to save and quit
    assert stop.is_set()
    with pytest.raises(KeyboardInterrupt):  # second: force
        handler(2, None)


def test_example_config_loads():
    cfg = load_config("config.example.toml")
    assert cfg.backend.type == "pyboy" and cfg.overlay.port == 8080


@pytest.mark.parametrize("line,hint", [
    ("channel = yourname", "text values need quotes"),
    ("channel = \u201cyourname\u201d", "curly quotes"),
])
def test_config_errors_point_at_the_line(tmp_path, line, hint):
    bad = tmp_path / "config.toml"
    bad.write_text(f"[twitch]\n{line}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match=hint):
        load_config(bad)


def test_unknown_config_keys_are_errors(tmp_path):
    bad = tmp_path / "config.toml"
    bad.write_text("[overlay]\ndir = \"overlay\"\n")
    with pytest.raises(SystemExit, match="dir"):
        load_config(bad)


def test_a_game_file_layers_on_the_main_config():
    cfg = load_config(["config.example.toml", "games/gta6.toml"])
    assert cfg.backend.type == "gamepad" and "goup" in cfg.allowed_commands
    assert cfg.twitch.channel == "your_channel_name"  # kept from the main config
    assert cfg.democracy.window_seconds == 5  # the game file wins where it says so
    assert cfg.meter.min_votes == 5


@pytest.mark.parametrize("command,error", [
    ('jump = { button = "Z" }', "button must be one of"),
    ('jump = { stick = "middle", y = 1 }', "stick must be"),
    ('jump = { stick = "left", y = 2 }', "between -1 and 1"),
    ('jump = { buton = "A" }', "unknown fields"),
    ('wait = { button = "A" }', "lowercase letters only"),
    ('jump = { seconds = 1 }', "needs a button"),
])
def test_bad_game_commands_are_explained(tmp_path, command, error):
    game = tmp_path / "game.toml"
    game.write_text(f'[backend]\ntype = "gamepad"\n[game.commands]\n{command}\n')
    with pytest.raises(SystemExit, match=error):
        load_config(game)


def test_commands_need_the_gamepad_backend(tmp_path):
    game = tmp_path / "game.toml"
    game.write_text('[game.commands]\njump = { button = "A" }\n')
    with pytest.raises(SystemExit, match="gamepad"):
        load_config(game)


def test_log_lines_are_prefixed_once(capsys):
    import logging

    from twitchplayeragent.__main__ import setup_logging

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
