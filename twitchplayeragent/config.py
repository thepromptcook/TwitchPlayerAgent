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
    type: str = "pyboy"  # "pyboy", "keyboard", or "log"
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
    def allowed_buttons(self) -> frozenset[str]:
        return frozenset(b.lower() for b in self.game.buttons)

    def validate(self) -> None:
        bad = [b for b in self.allowed_buttons if b not in ALL_BUTTONS]
        if bad:
            raise ValueError(f"Unknown buttons in [game].buttons: {bad}")
        if self.meter.start_mode not in ("anarchy", "democracy"):
            raise ValueError("[meter].start_mode must be 'anarchy' or 'democracy'")
        if self.backend.type not in ("pyboy", "keyboard", "log"):
            raise ValueError("[backend].type must be 'pyboy', 'keyboard', or 'log'")
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


def load_config(path: str | Path | None) -> Config:
    if path is None:
        cfg = Config()
    else:
        text = Path(path).read_text(encoding="utf-8")
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise SystemExit(_explain_toml_error(path, text, exc)) from None
        try:
            cfg = _build(Config, data)
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"Config error in {path}: {exc}") from None
    try:
        cfg.validate()
    except ValueError as exc:
        raise SystemExit(f"Config error in {path or 'defaults'}: {exc}") from None
    return cfg


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
