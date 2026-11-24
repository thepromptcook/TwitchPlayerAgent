"""Input backends: where button presses end up."""

from __future__ import annotations

from ..config import Config
from .base import Backend


def make_backend(cfg: Config) -> Backend:
    kind = cfg.backend.type
    if kind == "pyboy":
        from .pyboy_backend import PyBoyBackend

        return PyBoyBackend(cfg.backend.pyboy, cfg.backend.hold_frames, cfg.backend.release_frames)
    if kind == "keyboard":
        from .keyboard_backend import KeyboardBackend

        return KeyboardBackend(cfg.backend.keyboard)
    if kind == "log":
        from .log_backend import LogBackend

        return LogBackend()
    raise ValueError(f"Unknown backend type: {kind}")


__all__ = ["Backend", "make_backend"]
