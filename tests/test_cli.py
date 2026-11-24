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
