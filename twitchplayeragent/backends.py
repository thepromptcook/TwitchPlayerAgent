"""Input backends: where button presses end up.

* PyBoyBackend: runs the ROM inside PyBoy and presses buttons on exact frames.
* KeyboardBackend: sends keypresses to an external emulator window.
* LogBackend: dry run, only records/logs presses.

``press(button)`` blocks until the button is pressed *and released*; the engine
calls it from a worker thread, one press at a time.
"""

from __future__ import annotations

import faulthandler
import logging
import queue
import threading
import time
from pathlib import Path

from .config import Config, KeyboardConfig, PyBoyConfig

log = logging.getLogger(__name__)


class Backend:
    #: True if the backend must own the main thread (an SDL window, required on macOS).
    needs_main_thread = False
    #: Set by __main__ to Overlay.set_frame(width, height, rgba) if the backend has the
    #: game's pixels (PyBoy), so the overlay can show the game without window capture.
    on_frame = None
    #: Likewise Overlay.add_audio(rate, samples) for the game's sound (PyBoy).
    on_audio = None

    def start(self) -> None:
        """Called once before any press."""

    def stop(self) -> None:
        """Called once on shutdown."""

    def press(self, button: str) -> None:
        raise NotImplementedError

    def run_main_loop(self, stop: threading.Event) -> None:
        """For needs_main_thread backends: run until ``stop`` is set."""
        stop.wait()


class LogBackend(Backend):
    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.pressed: list[str] = []

    def press(self, button: str) -> None:
        self.pressed.append(button)
        time.sleep(self.delay)


class KeyboardBackend(Backend):
    """Keys into a focused emulator window (how the 2014 stream worked). On Windows,
    pydirectinput is preferred because many emulators ignore virtual-key events."""

    def __init__(self, cfg: KeyboardConfig) -> None:
        self.cfg = cfg

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
            raise SystemExit('Keyboard backend needs pydirectinput or pynput: pip install -e ".[keyboard]"') from exc
        kb = Controller()
        resolve = lambda k: getattr(Key, k) if len(k) > 1 and hasattr(Key, k) else k  # noqa: E731
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


class PyBoyBackend(Backend):
    """The emulator runs on the main thread; press() hands jobs to it through a queue."""

    needs_main_thread = True

    def __init__(self, cfg: PyBoyConfig, hold_frames: int = 2, release_frames: int = 2) -> None:
        self.cfg = cfg
        self.hold = max(1, hold_frames)
        self.total = self.hold + max(0, release_frames)
        self._jobs: "queue.Queue[tuple[str, threading.Event]]" = queue.Queue()
        self._running = threading.Event()

    def press(self, button: str) -> None:
        if not self._running.wait(timeout=30):
            log.warning("Emulator not running; dropped %s", button)
            return
        done = threading.Event()
        self._jobs.put((button, done))
        done.wait(timeout=10)

    def _save(self, pyboy) -> None:
        path = Path(self.cfg.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as fh:
            pyboy.save_state(fh)
        tmp.replace(path)  # atomic: a crash mid-save never corrupts the last good state
        log.info("Saved emulator state to %s", path)

    def run_main_loop(self, stop: threading.Event) -> None:
        try:
            from pyboy import PyBoy
        except ImportError as exc:
            raise SystemExit('PyBoy is not installed: pip install -e ".[pyboy]"') from exc
        rom = Path(self.cfg.rom)
        if not rom.is_file():
            raise SystemExit(f"ROM not found at {rom}. Put your own ROM there or set [backend.pyboy].rom.")

        # no_input: PyBoy's own keyboard controls are off, so keys typed into the game
        # window (Ctrl+C, whose "c" cycles the palette) can't play; only chat does.
        # But no_input also stops PyBoy reading the window's events at all, so Windows
        # marks the window "Not Responding" on a click and the close button / Ctrl+C
        # (SDL turns it into a quit event) are never seen. pump_window() below reads
        # them instead: input is dropped, quit ends the loop.
        # When the overlay carries the sound, mute the window: PyBoy's volume only scales
        # what the window plays, not the samples it hands us.
        pyboy = PyBoy(str(rom), window=self.cfg.window, scale=self.cfg.scale,
                      no_input=not self.cfg.window_keyboard,
                      sound_volume=0 if self.on_audio is not None else 100)
        pyboy.set_emulation_speed(1)  # real time
        state = Path(self.cfg.state_file)
        if state.is_file():
            with open(state, "rb") as fh:
                pyboy.load_state(fh)
            log.info("Loaded emulator state from %s", state)
        log.info("Game is running. Close the game window or press Ctrl+C to save and quit.")
        pump_window = _window_pump() if not self.cfg.window_keyboard and self.cfg.window == "SDL2" else None

        # Freeze report: if the loop stops ticking for 10 s, Python writes every thread's
        # stack to hang-report.txt next to the save, showing where it got stuck.
        state.parent.mkdir(parents=True, exist_ok=True)
        hang_report = open(state.parent / "hang-report.txt", "w")
        self._running.set()
        autosave = self.cfg.autosave_minutes * 60
        last_save = time.monotonic()
        job: tuple[str, threading.Event] | None = None
        frame = 0  # frames since the current job's button went down
        ticks = 0
        try:
            while not stop.is_set():
                if job is None and not self._jobs.empty():
                    job, frame = self._jobs.get_nowait(), 0
                    pyboy.button_press(job[0])
                if not pyboy.tick():  # False when PyBoy saw the window close
                    break
                if pump_window is not None and pump_window():  # we saw it close / Ctrl+C
                    break
                ticks += 1
                if ticks % 60 == 0:  # re-arm the watchdog every second
                    faulthandler.dump_traceback_later(10, file=hang_report)
                if self.on_frame is not None:  # every frame (60 fps) to the overlay
                    screen = pyboy.screen.ndarray  # live (144, 160, 4) RGBA view; tobytes copies
                    self.on_frame(screen.shape[1], screen.shape[0], screen.tobytes())
                if self.on_audio is not None:  # this frame's samples, interleaved stereo int8
                    sound = pyboy.sound
                    self.on_audio(sound.sample_rate, bytes(sound.raw_buffer[: sound.raw_buffer_head]))
                if job is not None:
                    frame += 1
                    if frame == self.hold:
                        pyboy.button_release(job[0])
                    if frame >= self.total:
                        job[1].set()
                        job = None
                if autosave > 0 and time.monotonic() - last_save >= autosave:
                    self._save(pyboy)
                    last_save = time.monotonic()
        finally:
            faulthandler.cancel_dump_traceback_later()
            hang_report.close()
            self._running.clear()
            stop.set()
            if job is not None:
                job[1].set()
            while not self._jobs.empty():
                self._jobs.get_nowait()[1].set()
            self._save(pyboy)
            pyboy.stop()


def _window_pump():
    """A function that reads the SDL window's pending events, drops them, and returns
    True on a quit event (close button or Ctrl+C). None if SDL isn't importable."""
    try:
        import sdl2  # PySDL2, installed with PyBoy
        import sdl2.ext
    except ImportError:
        return None

    def pump() -> bool:
        return any(e.type == sdl2.SDL_QUIT for e in sdl2.ext.get_events())

    return pump


def make_backend(cfg: Config) -> Backend:
    b = cfg.backend
    if b.type == "pyboy":
        return PyBoyBackend(b.pyboy, b.hold_frames, b.release_frames)
    if b.type == "keyboard":
        return KeyboardBackend(b.keyboard)
    return LogBackend()
