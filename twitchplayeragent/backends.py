"""Where presses end up. press(command) blocks until it's pressed and released; the engine calls
it from a worker thread, one press at a time. Design notes and past bugs: the core skill's
references/io.md."""

from __future__ import annotations

import faulthandler
import logging
import queue
import threading
import time
from pathlib import Path

from .config import PAD_BUTTONS, Config, KeyboardConfig, PyBoyConfig

log = logging.getLogger(__name__)


class Backend:
    needs_main_thread = False  # True: run_main_loop(stop) owns the main thread (SDL needs it)
    on_frame = None  # set by __main__ to Overlay.set_frame / Overlay.add_audio when the
    on_audio = None  # backend has the game's picture and sound (PyBoy)

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def press(self, command: str) -> None:
        raise NotImplementedError


class LogBackend(Backend):
    """--dry-run: only records presses."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay, self.pressed = delay, []

    def press(self, command: str) -> None:
        self.pressed.append(command)
        time.sleep(self.delay)


class KeyboardBackend(Backend):
    """Keys into a focused external emulator (mGBA), like the 2014 stream."""

    def __init__(self, cfg: KeyboardConfig) -> None:
        self.cfg = cfg

    def start(self) -> None:
        try:  # Windows: many emulators ignore virtual-key events, so DirectInput scan codes
            import pydirectinput  # type: ignore

            pydirectinput.PAUSE = 0
            self._down, self._up = pydirectinput.keyDown, pydirectinput.keyUp
        except ImportError:
            try:
                from pynput.keyboard import Controller, Key  # type: ignore
            except ImportError as exc:
                raise SystemExit('Keyboard backend needs pydirectinput or pynput: pip install -e ".[keyboard]"') from exc
            kb = Controller()
            key = lambda k: getattr(Key, k) if len(k) > 1 and hasattr(Key, k) else k  # noqa: E731
            self._down, self._up = (lambda k: kb.press(key(k))), (lambda k: kb.release(key(k)))

    def press(self, command: str) -> None:
        key = self.cfg.keys.get(command)
        if key is not None:
            self._down(key)
            time.sleep(self.cfg.hold_ms / 1000)
            self._up(key)
            time.sleep(self.cfg.gap_ms / 1000)


class GamepadBackend(Backend):
    """A virtual Xbox 360 controller (vgamepad + ViGEmBus) for [game.commands] games. Toggled
    buttons and stick positions stay held; a momentary command acts on top for `seconds`, so
    `left` steers while `drive` keeps the accelerator down."""

    GAP = 0.05  # seconds between commands

    def __init__(self, commands: dict[str, dict]) -> None:
        self.commands, self.pad = commands, None
        self.held: set[str] = set()  # toggled buttons
        self.sticks: dict[str, tuple[float, float]] = {}  # toggled stick positions

    def start(self) -> None:
        try:
            import vgamepad
        except ImportError as exc:
            raise SystemExit('Controller games need vgamepad: pip install -e ".[gamepad]" '
                             "(Windows; it also installs the ViGEmBus driver)") from exc
        self.buttons = {b: getattr(vgamepad.XUSB_BUTTON, "XUSB_GAMEPAD_" + x) for b, x in PAD_BUTTONS.items() if x}
        self.pad = vgamepad.VX360Gamepad()
        self._apply(set(), {})
        log.info("Virtual Xbox controller connected. If the Xbox app was already open, quit it "
                 "completely (tray icon or Task Manager) and reopen it so Remote Play sees it.")

    def stop(self) -> None:
        if self.pad is not None:  # let go of everything when the bot exits
            self.pad.reset()
            self.pad.update()

    def press(self, command: str) -> None:
        spec = self.commands.get(command)
        if spec is None:
            return
        buttons = {spec["button"]} if "button" in spec else set()
        sticks = {spec["stick"]: (float(spec.get("x", 0)), float(spec.get("y", 0)))} if "stick" in spec else {}
        if spec.get("release"):
            self.held.clear()
            self.sticks.clear()
        elif spec.get("toggle"):
            if buttons <= self.held and sticks.items() <= self.sticks.items():  # repeated: off
                self.held -= buttons
                for stick in sticks:
                    del self.sticks[stick]
            else:  # on; a new direction on the same stick replaces the old one
                self.held |= buttons
                self.sticks.update(sticks)
        else:  # momentary, on top of what's toggled
            self._apply(self.held | buttons, {**self.sticks, **sticks})
            time.sleep(float(spec.get("seconds", 0.1)))
        self._apply(self.held, self.sticks)
        time.sleep(self.GAP)

    def _apply(self, buttons: set[str], sticks: dict[str, tuple[float, float]]) -> None:
        pad = self.pad
        for name, button in self.buttons.items():
            (pad.press_button if name in buttons else pad.release_button)(button=button)
        pad.left_trigger_float(value_float=float("LT" in buttons))
        pad.right_trigger_float(value_float=float("RT" in buttons))
        pad.left_joystick_float(*sticks.get("left", (0.0, 0.0)))
        pad.right_joystick_float(*sticks.get("right", (0.0, 0.0)))
        pad.update()


class PyBoyBackend(Backend):
    """Runs the ROM in PyBoy on the main thread. press() queues a (command, done) job, and the
    loop holds the button for exact frames."""

    needs_main_thread = True

    def __init__(self, cfg: PyBoyConfig, hold_frames: int = 2, release_frames: int = 2) -> None:
        self.cfg = cfg
        self.hold = max(1, hold_frames)
        self.total = self.hold + max(0, release_frames)
        self._jobs: queue.Queue[tuple[str, threading.Event]] = queue.Queue()
        self._running = threading.Event()

    def press(self, command: str) -> None:
        if not self._running.wait(timeout=30):
            log.warning("Emulator not running; dropped %s", command)
            return
        done = threading.Event()
        self._jobs.put((command, done))
        done.wait(timeout=10)

    def _save(self, pyboy) -> None:
        path = Path(self.cfg.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "wb") as fh:
            pyboy.save_state(fh)
        tmp.replace(path)  # atomic: a crash mid-save keeps the last good state
        log.info("Saved emulator state to %s", path)

    def _open(self):
        try:
            from pyboy import PyBoy
        except ImportError as exc:
            raise SystemExit('PyBoy is not installed: pip install -e ".[pyboy]"') from exc
        rom = Path(self.cfg.rom)
        if not rom.is_file():
            raise SystemExit(f"ROM not found at {rom}. Put your own ROM there or set [backend.pyboy].rom.")
        # no_input: only chat plays. sound_volume only scales the window's own playback, so
        # muting it keeps the overlay's sound and stops Desktop Audio doubling it.
        pyboy = PyBoy(str(rom), window=self.cfg.window, scale=self.cfg.scale,
                      no_input=not self.cfg.window_keyboard, sound_volume=0 if self.on_audio else 100)
        pyboy.set_emulation_speed(1)  # real time
        state = Path(self.cfg.state_file)
        if state.is_file():
            with open(state, "rb") as fh:
                pyboy.load_state(fh)
            log.info("Loaded emulator state from %s", state)
        return pyboy

    def _publish(self, pyboy) -> None:
        """This frame's picture and sound to the overlay."""
        if self.on_frame is not None:
            screen = pyboy.screen.ndarray  # a live (144, 160, 4) RGBA view: tobytes() copies it
            self.on_frame(screen.shape[1], screen.shape[0], screen.tobytes())
        if self.on_audio is not None:
            sound = pyboy.sound  # this frame's samples, interleaved stereo int8
            self.on_audio(sound.sample_rate, bytes(sound.raw_buffer[: sound.raw_buffer_head]))

    def run_main_loop(self, stop: threading.Event) -> None:
        pyboy = self._open()
        pump = _window_pump() if self.cfg.window == "SDL2" and not self.cfg.window_keyboard else None
        saves = Path(self.cfg.state_file).parent
        saves.mkdir(parents=True, exist_ok=True)
        hang_report = open(saves / "hang-report.txt", "w")  # every thread's stack after a 10 s stall
        autosave = self.cfg.autosave_minutes * 60
        next_save = time.monotonic() + autosave
        job, frame, ticks = None, 0, 0  # frame: frames since the job's button went down
        self._running.set()
        log.info("Game is running. Close the game window or press Ctrl+C to save and quit.")
        try:
            while not stop.is_set():
                if job is None and not self._jobs.empty():
                    job, frame = self._jobs.get_nowait(), 0
                    pyboy.button_press(job[0])
                if not pyboy.tick() or (pump and pump()):
                    break  # window closed, or Ctrl+C
                ticks += 1
                self._publish(pyboy)
                if job is not None:
                    frame += 1
                    if frame == self.hold:
                        pyboy.button_release(job[0])
                    if frame >= self.total:
                        job[1].set()
                        job = None
                if ticks % 60 == 0:  # once a second
                    faulthandler.dump_traceback_later(10, file=hang_report)
                    if autosave > 0 and time.monotonic() >= next_save:
                        self._save(pyboy)
                        next_save = time.monotonic() + autosave
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
    """Reads and drops the SDL window's events, True on quit (close button, Ctrl+C): no_input
    stops PyBoy reading them, and an unread window goes "Not Responding"."""
    try:
        import sdl2.ext  # PySDL2, installed with PyBoy
    except ImportError:
        return None
    return lambda: any(e.type == sdl2.SDL_QUIT for e in sdl2.ext.get_events())


def make_backend(cfg: Config) -> Backend:
    b = cfg.backend
    if b.type == "pyboy":
        return PyBoyBackend(b.pyboy, b.hold_frames, b.release_frames)
    if b.type == "keyboard":
        return KeyboardBackend(b.keyboard)
    return GamepadBackend(cfg.game.commands) if b.type == "gamepad" else LogBackend()
