"""Configuration, loaded from a TOML file (see config.example.toml)."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .commands import ALL_BUTTONS


@dataclass
class TwitchConfig:
    channel: str = ""  # chat is read anonymously; the bot never posts


POKEMON_RED_AI_NOTES = (
    "Original Game Boy game. Each press is one tap; one tap of a direction turns the "
    "player or moves one tile. A moves on through text and confirms menu choices, B "
    "cancels or goes back, and start opens the menu. Chat may say things like \"walk "
    "into the tall grass\", \"use thunderbolt\" or \"run away\"."
)


@dataclass
class GameConfig:
    name: str = "Pokemon Red"
    # Select was disabled during the original Red run after it was used to soft-reset.
    buttons: list[str] = field(
        default_factory=lambda: ["a", "b", "up", "down", "left", "right", "start"]
    )
    # Game knowledge for AI mode: what the buttons do and what chat may ask for.
    ai_notes: str = POKEMON_RED_AI_NOTES
    # Controller games (backend "gamepad"): chat command name -> what it does, replacing
    # the Game Boy buttons above. See check_command() for the fields; games/gta6.toml.
    commands: dict[str, dict] = field(default_factory=dict)


# Virtual Xbox controller buttons a [game.commands] entry can use (LT/RT are the triggers).
PAD_BUTTONS = ("A", "B", "X", "Y", "LB", "RB", "LT", "RT", "LS", "RS",
               "START", "BACK", "UP", "DOWN", "LEFT", "RIGHT")
RESERVED_WORDS = {"wait", "anarchy", "democracy"}  # chat words with a fixed meaning


def check_command(name: str, spec: dict) -> None:
    """One [game.commands] entry. Fields:
    button   one of PAD_BUTTONS          stick    "left" or "right", with x and y (-1..1)
    seconds  how long a press lasts (0.1)  toggle   stays held until repeated or `stop`
    release  true: let go of everything    description  shown to the AI"""
    if not re.fullmatch(r"[a-z]+", name) or name in RESERVED_WORDS:
        raise ValueError(f"command {name!r}: use lowercase letters only, not {sorted(RESERVED_WORDS)}")
    unknown = set(spec) - {"button", "stick", "x", "y", "seconds", "toggle", "release", "description"}
    if unknown:
        raise ValueError(f"command {name!r}: unknown fields {sorted(unknown)}")
    if spec.get("button") is not None and spec["button"] not in PAD_BUTTONS:
        raise ValueError(f"command {name!r}: button must be one of {list(PAD_BUTTONS)}")
    if spec.get("stick") is not None and spec["stick"] not in ("left", "right"):
        raise ValueError(f"command {name!r}: stick must be 'left' or 'right'")
    if not all(-1 <= float(spec.get(k, 0)) <= 1 for k in ("x", "y")):
        raise ValueError(f"command {name!r}: x and y must be between -1 and 1")
    if float(spec.get("seconds", 0.1)) <= 0:
        raise ValueError(f"command {name!r}: seconds must be positive")
    if not (spec.get("release") or "button" in spec or "stick" in spec):
        raise ValueError(f"command {name!r}: needs a button, a stick, or release = true")


@dataclass
class AnarchyConfig:
    # Inputs waiting to run. When full, the oldest are dropped so lag stays bounded.
    max_queue: int = 100


@dataclass
class DemocracyConfig:
    # Contemporary reports put the original round length at 10-30 seconds.
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
    # true: an AI reads all chat and picks the presses, instead of anarchy/democracy.
    enabled: bool = False
    provider: str = "claude"  # "claude" (Anthropic API) or "ollama" (local model)
    model: str = ""  # empty = claude-haiku-5-5 for claude, qwen3.5:27b for ollama
    effort: str = "low"  # claude only
    ollama_url: str = "http://localhost:11434"
    window_seconds: float = 10.0  # chat per decision
    max_presses: int = 9  # per decision


@dataclass
class PyBoyConfig:
    rom: str = "roms/pokemon_red.gb"
    state_file: str = "saves/pokemon_red.state"
    autosave_minutes: float = 5.0
    window: str = "SDL2"  # "null" for headless
    scale: int = 4
    # Let your own keyboard play the game when its window is focused. Off by
    # default so stray keys (e.g. Ctrl+C) can't press buttons; only chat plays.
    window_keyboard: bool = False


@dataclass
class KeyboardConfig:
    # Game Boy button -> key bound in your emulator (mGBA / VisualBoyAdvance / BizHawk).
    keys: dict[str, str] = field(
        default_factory=lambda: {
            "a": "x", "b": "z", "start": "enter", "select": "backspace",
            "up": "up", "down": "down", "left": "left", "right": "right",
        }
    )
    hold_ms: int = 50
    gap_ms: int = 50


@dataclass
class BackendConfig:
    type: str = "pyboy"  # "pyboy", "keyboard", "gamepad" (virtual Xbox controller), or "log"
    # PyBoy timing in frames (60/s). Tune if inputs are dropped or feel sluggish.
    hold_frames: int = 2
    release_frames: int = 2
    pyboy: PyBoyConfig = field(default_factory=PyBoyConfig)
    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)


@dataclass
class OverlayConfig:
    # A local web page for one OBS Browser Source: http://localhost:<port>/
    enabled: bool = True
    port: int = 8080
    max_lines: int = 20
    # Game sound plays through the Browser Source, and the game window itself is muted
    # so OBS's Desktop Audio doesn't capture it twice. false = sound from the window.
    audio: bool = True
    # Scrolling message along the bottom. Change it mid-stream by typing "!ticker <text>"
    # in your own chat (you or a moderator); "!ticker" alone clears it. The latest one is
    # saved to ticker_file, so it survives a restart (delete the file to use this again).
    ticker: str = ""
    ticker_file: str = "saves/ticker.txt"


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
        """The chat words that press something: [game.commands] names, else the Game Boy buttons."""
        if self.game.commands:
            return frozenset(self.game.commands)
        return frozenset(b.lower() for b in self.game.buttons)

    def validate(self) -> None:
        if self.game.commands:
            for name, spec in self.game.commands.items():
                check_command(name, spec)
            if self.backend.type not in ("gamepad", "log"):
                raise ValueError("[game.commands] need [backend].type = 'gamepad'")
        else:
            bad = [b for b in self.allowed_commands if b not in ALL_BUTTONS]
            if bad:
                raise ValueError(f"Unknown buttons in [game].buttons: {bad}")
            if self.backend.type == "gamepad":
                raise ValueError("[backend].type 'gamepad' needs a [game.commands] table")
        if self.meter.start_mode not in ("anarchy", "democracy"):
            raise ValueError("[meter].start_mode must be 'anarchy' or 'democracy'")
        if self.backend.type not in ("pyboy", "keyboard", "gamepad", "log"):
            raise ValueError("[backend].type must be 'pyboy', 'keyboard', 'gamepad', or 'log'")
        if not 0 < self.meter.to_democracy <= 1 or not 0 < self.meter.to_anarchy <= 1:
            raise ValueError("[meter] thresholds must be between 0 and 1")
        if self.ai.provider not in ("claude", "ollama"):
            raise ValueError("[ai].provider must be 'claude' or 'ollama'")
        if self.ai.window_seconds <= 0 or self.ai.max_presses < 1:
            raise ValueError("[ai] window_seconds and max_presses must be positive")


def _build(cls: type, data: dict[str, Any]) -> Any:
    known = {f.name: f for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ValueError(f"Unknown keys for {cls.__name__}: {sorted(unknown)}")
    kwargs = {}
    defaults = cls()
    for name, value in data.items():
        current = getattr(defaults, name)
        if is_dataclass(current) and isinstance(value, dict):
            kwargs[name] = _build(type(current), value)
        else:
            kwargs[name] = value
    return cls(**kwargs)


def load_config(paths: str | Path | list | None) -> Config:
    """Load one TOML file, or several merged in order so later files win: e.g.
    [config.toml, games/gta6.toml] keeps your channel and overlay but plays GTA VI."""
    if paths is None:
        paths = []
    elif isinstance(paths, (str, Path)):
        paths = [paths]
    data: dict[str, Any] = {}
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        try:
            _merge(data, tomllib.loads(text))
        except tomllib.TOMLDecodeError as exc:
            raise SystemExit(_explain_toml_error(path, text, exc)) from None
    where = " + ".join(str(p) for p in paths) or "defaults"
    try:
        cfg = _build(Config, data)
        cfg.validate()
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"Config error in {where}: {exc}") from None
    return cfg


def _merge(base: dict, extra: dict) -> None:
    """Deep-merge ``extra`` into ``base``. A command table is replaced whole, so a game
    file's [game.commands] never mixes with another game's."""
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict) and key != "commands":
            _merge(base[key], value)
        else:
            base[key] = value


def _explain_toml_error(path: str | Path, text: str, exc: "tomllib.TOMLDecodeError") -> str:
    lineno = getattr(exc, "lineno", None)
    if lineno is None:  # Python < 3.14 only has it in the message text
        m = re.search(r"line (\d+)", str(exc))
        lineno = int(m.group(1)) if m else None
    msg = f"Could not read {path}: {exc}"
    lines = text.splitlines()
    if not lineno or not 0 < lineno <= len(lines):
        return msg
    line = lines[lineno - 1]
    msg += f"\n  line {lineno}:  {line.strip()}"
    value = line.partition("=")[2].strip()
    if any(q in line for q in "“”‘’"):
        msg += "\n  Hint: that line has curly quotes. Use plain straight quotes: \"like this\""
    elif value and value[0] not in "\"'[{" and not value[0].isdigit() and value.split()[0] not in ("true", "false"):
        msg += "\n  Hint: text values need quotes, e.g.  channel = \"yourname\""
    return msg
