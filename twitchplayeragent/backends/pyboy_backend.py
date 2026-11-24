"""Run Pokémon Red inside PyBoy (a Python Game Boy emulator) and drive it directly.

Driving the emulator in-process means inputs land on exact frames, which is
far more reliable than faking keypresses into a separate emulator window.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PyBoyConfig
from .base import Backend

log = logging.getLogger(__name__)


@dataclass
class _Job:
    button: str
    done: threading.Event = field(default_factory=threading.Event)
    phase: str = "pending"  # pending -> hold -> gap
    frames_left: int = 0


class PyBoyBackend(Backend):
    # SDL windows must live on the main thread (required on macOS).
    needs_main_thread = True

    def __init__(self, cfg: PyBoyConfig, hold_frames: int = 2, release_frames: int = 2) -> None:
        self.cfg = cfg
        self.hold_frames = max(1, hold_frames)
        self.release_frames = max(0, release_frames)
        self._jobs: "queue.Queue[_Job]" = queue.Queue()
        self._running = threading.Event()

    def press(self, button: str) -> None:
        if not self._running.wait(timeout=30):
            log.warning("Emulator not running; dropped %s", button)
            return
        job = _Job(button)
        self._jobs.put(job)
        job.done.wait(timeout=10)

    def _save_state(self, pyboy) -> None:
        path = Path(self.cfg.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as fh:
            pyboy.save_state(fh)
        tmp.replace(path)
        log.info("Saved emulator state to %s", path)

    def run_main_loop(self, stop: threading.Event) -> None:
        try:
            from pyboy import PyBoy
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise SystemExit("PyBoy is not installed. Run: pip install pyboy") from exc

        rom = Path(self.cfg.rom)
        if not rom.is_file():
            raise SystemExit(
                f"ROM not found at {rom}. Put your own Pokémon Red ROM there or set "
                "[backend.pyboy].rom in your config."
            )

        pyboy = PyBoy(
            str(rom),
            window=self.cfg.window,
            scale=self.cfg.scale,
            no_input=not self.cfg.window_keyboard,
        )
        pyboy.set_emulation_speed(1)  # real time, like a real Game Boy
        log.info("Pokémon Red is running. Close the game window to save and quit.")

        state = Path(self.cfg.state_file)
        if state.is_file():
            with open(state, "rb") as fh:
                pyboy.load_state(fh)
            log.info("Loaded emulator state from %s", state)

        self._running.set()
        autosave_every = self.cfg.autosave_minutes * 60
        last_save = time.monotonic()
        job: _Job | None = None
        try:
            while not stop.is_set():
                if job is None:
                    try:
                        job = self._jobs.get_nowait()
                    except queue.Empty:
                        job = None
                    if job is not None:
                        pyboy.button_press(job.button)
                        job.phase, job.frames_left = "hold", self.hold_frames

                if not pyboy.tick():  # False when the window is closed
                    break

                if job is not None:
                    job.frames_left -= 1
                    if job.frames_left <= 0:
                        if job.phase == "hold":
                            pyboy.button_release(job.button)
                            job.phase, job.frames_left = "gap", self.release_frames
                        if job.phase == "gap" and job.frames_left <= 0:
                            job.done.set()
                            job = None

                if autosave_every > 0 and time.monotonic() - last_save >= autosave_every:
                    self._save_state(pyboy)
                    last_save = time.monotonic()
        finally:
            self._running.clear()
            stop.set()
            if job is not None:
                job.done.set()
            while not self._jobs.empty():
                self._jobs.get_nowait().done.set()
            self._save_state(pyboy)
            pyboy.stop()
