from __future__ import annotations

import threading
from abc import ABC, abstractmethod


class Backend(ABC):
    """Something that can press Game Boy buttons.

    ``press`` blocks until the button has been pressed *and released*, so
    callers get one clean, ordered input at a time. It is called from a worker
    thread, never from the asyncio loop directly.
    """

    #: True if the backend must own the main thread (e.g. an SDL window on macOS).
    needs_main_thread: bool = False

    def start(self) -> None:
        """Prepare the backend. Called once before any press."""

    def stop(self) -> None:
        """Release resources. Called once on shutdown."""

    @abstractmethod
    def press(self, button: str) -> None:
        """Press and release ``button`` (one of commands.ALL_BUTTONS)."""

    def run_main_loop(self, stop: threading.Event) -> None:
        """For backends with needs_main_thread: run until ``stop`` is set."""
        stop.wait()
