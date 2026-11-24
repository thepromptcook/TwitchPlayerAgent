"""PyBoyBackend's main loop, driven by a fake `pyboy` module (no ROM or emulator needed)."""

import sys
import threading
import time
import types

from twitchplayeragent.backends import PyBoyBackend
from twitchplayeragent.config import PyBoyConfig


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
    assert len(frames) == (emu.frame - 1) // 2  # every other frame (30 fps); none after close
    assert audio and set(audio) == {(48000, 1600)}  # every frame's samples
    assert (tmp_path / "saves" / "red.state").read_bytes() == b"state"  # saved on exit
    assert emu.stopped and stop.is_set()
