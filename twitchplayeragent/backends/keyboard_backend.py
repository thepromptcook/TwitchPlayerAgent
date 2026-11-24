"""Send keypresses to an external emulator window (mGBA, VisualBoyAdvance, BizHawk...).

This is how the original 2014 stream worked: a bot pressing keys in an
emulator. Keep the emulator window focused. On Windows, pydirectinput is
preferred because many emulators ignore virtual-key events; elsewhere pynput.
"""

from __future__ import annotations

import time

from ..config import KeyboardConfig
from .base import Backend


class KeyboardBackend(Backend):
    def __init__(self, cfg: KeyboardConfig) -> None:
        self.cfg = cfg
        self._down = None
        self._up = None

    def start(self) -> None:
        try:
            import pydirectinput  # type: ignore

            pydirectinput.PAUSE = 0
            self._down, self._up = pydirectinput.keyDown, pydirectinput.keyUp
            return
        except ImportError:
            pass
        try:
            from pynput.keyboard import Controller, Key  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "Keyboard backend needs pydirectinput (Windows) or pynput. "
                "Run: pip install pydirectinput  (or)  pip install pynput"
            ) from exc

        kb = Controller()

        def resolve(name: str):
            return getattr(Key, name) if len(name) > 1 and hasattr(Key, name) else name

        self._down = lambda k: kb.press(resolve(k))
        self._up = lambda k: kb.release(resolve(k))

    def press(self, button: str) -> None:
        key = self.cfg.keys.get(button)
        if key is None:
            return
        self._down(key)
        time.sleep(self.cfg.hold_ms / 1000)
        self._up(key)
        time.sleep(self.cfg.gap_ms / 1000)
