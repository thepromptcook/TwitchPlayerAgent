"""TOML config -> dataclasses. What every field does, with its default, is in config.example.toml
(tests/test_docs.py keeps the two equal); [game.commands] fields are at the top of games/gta6.toml."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .commands import ALL_BUTTONS


@dataclass
class TwitchConfig:
    channel: str = ""


@dataclass
class GameConfig:
    name: str = "Pokemon Red"
    buttons: list[str] = field(default_factory=lambda: ["a", "b", "up", "down", "left", "right", "start"])
    ai_notes: str = (
        "Original Game Boy game. Each press is one tap; one tap of a direction turns the "
        "player or moves one tile. A moves on through text and confirms menu choices, B "
        "cancels or goes back, and start opens the menu. Chat may say things like \"walk "
        "into the tall grass\", \"use thunderbolt\" or \"run away\"."
    )
    commands: dict[str, dict] = field(default_factory=dict)


@dataclass
class AnarchyConfig:
    max_queue: int = 100


@dataclass
class DemocracyConfig:
    window_seconds: float = 20.0
    max_presses: int = 9


@dataclass
class MeterConfig:
    to_democracy: float = 0.80
    to_anarchy: float = 0.50
    vote_lifetime: float = 60.0
    min_votes: int = 5
    start_mode: str = "anarchy"


@dataclass
class AIConfig:
    enabled: bool = False
    provider: str = "claude"
    model: str = ""
    effort: str = "low"
    ollama_url: str = "http://localhost:11434"
    window_seconds: float = 10.0
    max_presses: int = 9


@dataclass
class PyBoyConfig:
    rom: str = "roms/pokemon_red.gb"
    state_file: str = "saves/pokemon_red.state"
    autosave_minutes: float = 5.0
    window: str = "SDL2"
    scale: int = 4
    window_keyboard: bool = False


@dataclass
class KeyboardConfig:
    keys: dict[str, str] = field(default_factory=lambda: {
        "a": "x", "b": "z", "start": "enter", "select": "backspace",
        "up": "up", "down": "down", "left": "left", "right": "right"})
    hold_ms: int = 50
    gap_ms: int = 50


@dataclass
class BackendConfig:
    type: str = "pyboy"
    hold_frames: int = 2
    release_frames: int = 2
    pyboy: PyBoyConfig = field(default_factory=PyBoyConfig)
    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)


@dataclass
class OverlayConfig:
    enabled: bool = True
    port: int = 8080
    max_lines: int = 20
    audio: bool = True
    ticker: str = ""
    ticker_file: str = "saves/ticker.txt"


# Buttons a [game.commands] entry can use -> vgamepad's XUSB_GAMEPAD_<name> ("": LT/RT, the triggers)
PAD_BUTTONS = {"A": "A", "B": "B", "X": "X", "Y": "Y", "LB": "LEFT_SHOULDER", "RB": "RIGHT_SHOULDER",
               "LT": "", "RT": "", "LS": "LEFT_THUMB", "RS": "RIGHT_THUMB", "START": "START", "BACK": "BACK",
               "UP": "DPAD_UP", "DOWN": "DPAD_DOWN", "LEFT": "DPAD_LEFT", "RIGHT": "DPAD_RIGHT"}
COMMAND_FIELDS = {"button", "stick", "x", "y", "seconds", "toggle", "release", "description"}


def _require(rules: list[tuple[Any, str]], prefix: str = "") -> None:
    for ok, problem in rules:
        if not ok:
            raise ValueError(prefix + problem)


def check_command(name: str, spec: Any) -> None:
    """One [game.commands] entry."""
    if not isinstance(spec, dict):
        raise ValueError(f"command {name!r}: write it as a table, e.g. {{ button = \"A\" }}")
    _require([
        (re.fullmatch(r"[a-z]+", name) and name not in ("wait", "anarchy", "democracy"),
         "use lowercase letters only, not wait, anarchy or democracy"),
        (set(spec) <= COMMAND_FIELDS, f"unknown fields {sorted(set(spec) - COMMAND_FIELDS)}"),
        (spec.get("button", "A") in PAD_BUTTONS, f"button must be one of {list(PAD_BUTTONS)}"),
        (spec.get("stick", "left") in ("left", "right"), "stick must be 'left' or 'right'"),
        (all(-1 <= float(spec.get(k, 0)) <= 1 for k in "xy"), "x and y must be between -1 and 1"),
        (float(spec.get("seconds", 0.1)) > 0, "seconds must be positive"),
        (spec.get("release") or "button" in spec or "stick" in spec, "needs a button, a stick, or release = true"),
    ], f"command {name!r}: ")


@dataclass
class Config:
    twitch: TwitchConfig = field(default_factory=TwitchConfig)
    game: GameConfig = field(default_factory=GameConfig)
    anarchy: AnarchyConfig = field(default_factory=AnarchyConfig)
    democracy: DemocracyConfig = field(default_factory=DemocracyConfig)
    meter: MeterConfig = field(default_factory=MeterConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)

    @property
    def allowed_commands(self) -> frozenset[str]:
        """The chat words that press something: the [game.commands] names, else [game].buttons."""
        return frozenset(self.game.commands or (b.lower() for b in self.game.buttons))

    def validate(self) -> None:
        game, backend, meter, ai = self.game, self.backend.type, self.meter, self.ai
        for name, spec in game.commands.items():
            check_command(name, spec)
        bad_buttons = sorted(set(self.allowed_commands) - set(ALL_BUTTONS))
        _require([
            (backend in ("pyboy", "keyboard", "gamepad", "log"),
             "[backend].type must be 'pyboy', 'keyboard', 'gamepad' or 'log'"),
            (not game.commands or backend in ("gamepad", "log"), "[game.commands] need [backend].type = 'gamepad'"),
            (game.commands or backend != "gamepad", "[backend].type 'gamepad' needs a [game.commands] table"),
            (game.commands or not bad_buttons, f"unknown buttons in [game].buttons: {bad_buttons}"),
            (meter.start_mode in ("anarchy", "democracy"), "[meter].start_mode must be 'anarchy' or 'democracy'"),
            (0 < meter.to_democracy <= 1 and 0 < meter.to_anarchy <= 1, "[meter] thresholds must be between 0 and 1"),
            (ai.provider in ("claude", "ollama"), "[ai].provider must be 'claude' or 'ollama'"),
            (ai.window_seconds > 0 and ai.max_presses >= 1, "[ai] window_seconds and max_presses must be positive"),
        ])


def load_config(paths: str | Path | list | None = None) -> Config:
    """TOML files merged in order, later winning: [config.toml, games/gta6.toml] keeps your channel
    and overlay but plays GTA VI. A [game.commands] table is replaced whole, never mixed."""
    paths = [paths] if isinstance(paths, (str, Path)) else list(paths or [])
    data: dict[str, Any] = {}
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8")
            _merge(data, tomllib.loads(text))
        except OSError as exc:
            raise SystemExit(f"Can't read the config file {path}: {exc.strerror}") from None
        except tomllib.TOMLDecodeError as exc:
            raise SystemExit(_explain_toml_error(path, text, exc)) from None
    try:
        cfg = _build(Config, data)
        cfg.validate()
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Config error in {' + '.join(map(str, paths)) or 'defaults'}: {exc}") from None
    return cfg


def _merge(base: dict, extra: dict) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict) and key != "commands":
            _merge(base[key], value)
        else:
            base[key] = value


def _build(cls: type, data: dict[str, Any], section: str = "") -> Any:
    """A dataclass from a TOML table; nested tables become nested dataclasses."""
    unknown = set(data) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f"unknown keys in {f'[{section}]' if section else 'the top level'}: {sorted(unknown)}")
    defaults, kwargs = cls(), {}
    for key, value in data.items():
        default = getattr(defaults, key)
        nested = is_dataclass(default) and isinstance(value, dict)
        kwargs[key] = _build(type(default), value, f"{section}.{key}".lstrip(".")) if nested else value
    return cls(**kwargs)


def _explain_toml_error(path: str | Path, text: str, exc: tomllib.TOMLDecodeError) -> str:
    """The error, the line it's on, and a hint for the two usual mistakes."""
    msg = f"Could not read {path}: {exc}"
    m = re.search(r"line (\d+)", str(exc))
    lines = text.splitlines()
    if not m or not 0 < int(m.group(1)) <= len(lines):
        return msg
    line = lines[int(m.group(1)) - 1]
    msg += f"\n  line {m.group(1)}:  {line.strip()}"
    value = line.partition("=")[2].strip()
    if any(q in line for q in "“”‘’"):
        msg += '\n  Hint: that line has curly quotes. Use plain straight quotes: "like this"'
    elif value and value[0] not in "\"'[{" and not value[0].isdigit() and value.split()[0] not in ("true", "false"):
        msg += '\n  Hint: text values need quotes, e.g.  channel = "yourname"'
    return msg
