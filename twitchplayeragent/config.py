"""Configuration, loaded from a TOML file (see config.example.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from .commands import ALL_BUTTONS


@dataclass
class TwitchConfig:
    channel: str = ""
    # Leave nick/oauth_token empty to read chat anonymously (read-only is all we need).
    nick: str = ""
    oauth_token: str = ""
    host: str = "irc.chat.twitch.tv"
    port: int = 6697


@dataclass
class GameConfig:
    name: str = "Pokemon Red"
    # Select was disabled during the original Red run after it was used to soft-reset.
    buttons: list[str] = field(
        default_factory=lambda: ["a", "b", "up", "down", "left", "right", "start"]
    )


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
class PyBoyConfig:
    rom: str = "roms/pokemon_red.gb"
    state_file: str = "saves/pokemon_red.state"
    autosave_minutes: float = 5.0
    window: str = "SDL2"  # "null" for headless
    scale: int = 4


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
    enabled: bool = True
    dir: str = "overlay"
    max_lines: int = 20


@dataclass
class Config:
    twitch: TwitchConfig = field(default_factory=TwitchConfig)
    game: GameConfig = field(default_factory=GameConfig)
    anarchy: AnarchyConfig = field(default_factory=AnarchyConfig)
    democracy: DemocracyConfig = field(default_factory=DemocracyConfig)
    meter: MeterConfig = field(default_factory=MeterConfig)
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
        with open(path, "rb") as fh:
            cfg = _build(Config, tomllib.load(fh))
    cfg.validate()
    return cfg
