"""PyBoyBackend's main loop, driven by a fake `pyboy` module (no ROM or emulator needed)."""

import sys
import threading
import time
import types

import pytest

from twitchplayeragent.backends import PyBoyBackend
from twitchplayeragent.config import PyBoyConfig, load_config


class FakeScreen:
    shape = (144, 160, 4)

    def tobytes(self):
        return bytes(160 * 144 * 4)


class FakePyBoy:
    def __init__(self, rom, **kwargs):
        self.kwargs, self.events, self.frame = kwargs, [], 0
        self.screen = types.SimpleNamespace(ndarray=FakeScreen())
        # 800 stereo samples per frame (48 kHz / 60), interleaved int8, as PyBoy exposes them
        self.sound = types.SimpleNamespace(sample_rate=48000, raw_buffer=memoryview(bytearray(4096)),
                                           raw_buffer_head=1600)

    def set_emulation_speed(self, speed): pass
    def button_press(self, b): self.events.append((self.frame, "down", b))
    def button_release(self, b): self.events.append((self.frame, "up", b))
    def save_state(self, fh): fh.write(b"state")
    def load_state(self, fh): self.loaded = fh.read()
    def stop(self): self.stopped = True

    def tick(self):
        time.sleep(0.001)  # a fast but real clock, so the press thread gets to run
        self.frame += 1
        done = len(self.events) == 4 and self.frame > self.events[-1][0] + 10
        return not done and self.frame < 5000  # then the "window closes"


def test_pyboy_loop_presses_frames_and_saves(tmp_path, monkeypatch):
    rom = tmp_path / "red.gb"
    rom.write_bytes(b"rom")
    instances = []
    monkeypatch.setitem(sys.modules, "pyboy", types.SimpleNamespace(
        PyBoy=lambda *a, **k: instances.append(FakePyBoy(*a, **k)) or instances[-1]))

    cfg = PyBoyConfig(rom=str(rom), state_file=str(tmp_path / "saves" / "red.state"))
    backend = PyBoyBackend(cfg, hold_frames=2, release_frames=3)
    frames, audio = [], []
    backend.on_frame = lambda w, h, data: frames.append((w, h, len(data)))
    backend.on_audio = lambda rate, data: audio.append((rate, len(data)))

    stop = threading.Event()
    presser = threading.Thread(target=lambda: [backend.press(b) for b in ("a", "up")])
    presser.start()
    backend.run_main_loop(stop)  # returns when the fake window "closes"
    presser.join(timeout=5)

    emu = instances[0]
    assert emu.kwargs["no_input"] is True  # the game window ignores the keyboard
    assert emu.kwargs["sound_volume"] == 0  # sound goes to the overlay, so the window is muted
    (d1, _, b1), (u1, _, _), (d2, _, b2), (u2, _, _) = emu.events
    assert (b1, b2) == ("a", "up")
    assert u1 - d1 == 2  # held for hold_frames
    assert d2 - d1 >= 5  # next press never before hold + release frames
    assert frames and frames[0] == (160, 144, 160 * 144 * 4)
    assert len(frames) == emu.frame - 1  # every frame (60 fps); none after the window closes
    assert audio and set(audio) == {(48000, 1600)}  # every frame's samples
    assert (tmp_path / "saves" / "red.state").read_bytes() == b"state"  # saved on exit
    assert emu.stopped and stop.is_set()


def test_window_events_are_read_and_quit_closes_cleanly(tmp_path, monkeypatch):
    """With no_input, PyBoy stops reading window events, so the bot must: otherwise
    Windows marks the window "Not Responding" and Ctrl+C / close are never seen."""
    rom = tmp_path / "red.gb"
    rom.write_bytes(b"rom")

    class EndlessPyBoy(FakePyBoy):
        def tick(self):
            self.frame += 1
            return self.frame < 10_000  # PyBoy itself never notices the close

    pumps = []

    def get_events():
        pumps.append(1)
        return [types.SimpleNamespace(type=256)] if len(pumps) == 30 else [types.SimpleNamespace(type=768)]

    sdl2 = types.ModuleType("sdl2")
    sdl2.SDL_QUIT = 256
    sdl2.ext = types.SimpleNamespace(get_events=get_events)
    monkeypatch.setitem(sys.modules, "sdl2", sdl2)
    monkeypatch.setitem(sys.modules, "sdl2.ext", sdl2.ext)
    emus = []
    monkeypatch.setitem(sys.modules, "pyboy", types.SimpleNamespace(
        PyBoy=lambda *a, **k: emus.append(EndlessPyBoy(*a, **k)) or emus[-1]))

    cfg = PyBoyConfig(rom=str(rom), state_file=str(tmp_path / "red.state"))
    stop = threading.Event()
    PyBoyBackend(cfg).run_main_loop(stop)

    assert len(pumps) == 30 and emus[0].frame == 30  # events read every frame; quit at frame 30
    assert (tmp_path / "red.state").read_bytes() == b"state" and stop.is_set()  # saved, stopped


# ---- GamepadBackend (virtual Xbox controller) -------------------------------------------

from twitchplayeragent.backends import GamepadBackend  # noqa: E402
from twitchplayeragent.config import PAD_BUTTONS  # noqa: E402


class FakePad:
    """Records the controller state sent with each update(), like vgamepad.VX360Gamepad."""

    def __init__(self):
        self.buttons, self.lt, self.rt, self.left, self.right = set(), 0.0, 0.0, (0.0, 0.0), (0.0, 0.0)
        self.sent = []

    def press_button(self, button): self.buttons.add(button)
    def release_button(self, button): self.buttons.discard(button)
    def left_trigger_float(self, value_float): self.lt = value_float
    def right_trigger_float(self, value_float): self.rt = value_float
    def left_joystick_float(self, x_value_float, y_value_float): self.left = (x_value_float, y_value_float)
    def right_joystick_float(self, x_value_float, y_value_float): self.right = (x_value_float, y_value_float)
    def reset(self): self.__init__()

    def update(self):
        names = {b.replace("XUSB_GAMEPAD_", "") for b in self.buttons}
        self.sent.append((names, self.lt, self.rt, self.left, self.right))


@pytest.fixture
def gamepad(monkeypatch):
    fake = types.SimpleNamespace(VX360Gamepad=FakePad, XUSB_BUTTON=types.SimpleNamespace(
        **{m: m for m in GamepadBackend.XUSB.values()}))
    monkeypatch.setitem(sys.modules, "vgamepad", fake)
    monkeypatch.setattr(GamepadBackend, "GAP", 0)
    cfg = load_config(["config.example.toml", "games/gta6.toml"])
    backend = GamepadBackend(cfg.game.commands)
    backend.start()
    return backend


def test_every_pad_button_maps_to_the_controller():
    assert set(GamepadBackend.XUSB) | {"LT", "RT"} == set(PAD_BUTTONS)


def test_gamepad_momentary_toggle_and_stop(gamepad):
    pad = gamepad.pad
    gamepad.press("jump")  # tap A, then let go
    assert pad.sent[-2][0] == {"A"} and pad.sent[-1][0] == set()
    gamepad.press("drive")  # RT stays down
    gamepad.press("left")  # steer while accelerating, then back to straight
    assert pad.sent[-2][2:4] == (1.0, (-1.0, 0.0)) and pad.sent[-1][2:4] == (1.0, (0.0, 0.0))
    gamepad.press("goup")  # walking forward stays on...
    gamepad.press("goleft")  # ...a new direction on the same stick replaces it
    assert pad.sent[-1][3] == (-1.0, 0.0)
    gamepad.press("goleft")  # same command again: off
    assert pad.sent[-1][3] == (0.0, 0.0) and pad.sent[-1][2] == 1.0  # still driving
    gamepad.press("stop")  # let go of everything
    assert pad.sent[-1] == (set(), 0.0, 0.0, (0.0, 0.0), (0.0, 0.0))
    gamepad.press("sprint")  # stick and LS together
    assert pad.sent[-1][0] == {"LEFT_THUMB"} and pad.sent[-1][3] == (0.0, 1.0)
    gamepad.stop()  # exiting releases everything
    assert pad.sent[-1] == (set(), 0.0, 0.0, (0.0, 0.0), (0.0, 0.0))
