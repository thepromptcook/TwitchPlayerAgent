# Gotchas: bugs already found (most only show on Windows or in OBS)

Each looked fine in Linux tests. Don't undo these fixes.

## PyBoy and Windows
- **`no_input` stops PyBoy reading window events entirely.** The window went "Not Responding"
  when clicked, and close / Ctrl+C (an SDL quit event) were never seen. Fix: `_window_pump()`
  reads `sdl2.ext.get_events()` every frame, drops input, stops on `SDL_QUIT`.
- **Ctrl+C took many presses.** A `KeyboardInterrupt` landing in PyBoy's Cython
  `frame_limiter` prints "Exception ignored" and is swallowed. Fix: `stop_on_ctrl_c` handles
  SIGINT by setting `stop`.
- **Console QuickEdit:** a click in a Windows terminal pauses every program writing to it.
  Fixes: `disable_quick_edit()` and queued logging, so a log call can't block the game loop.
- **`SO_REUSEADDR` on Windows** lets a second program bind a busy port silently. The overlay
  server turns it off on Windows only (elsewhere it just skips TIME_WAIT after a restart).
- **PyBoy's `sound_volume`** scales only the window's playback, not `pyboy.sound`, so muting the
  window keeps the overlay's sound intact and stops Desktop Audio doubling it.
- **Keys typed into the game window** would play and Ctrl+C's `c` cycles PyBoy's palette, hence
  `no_input` (with the pump above). Keyboard focus also explains why mGBA via `KeyboardBackend`
  must stay focused.
- **SDL windows need the main thread** (macOS): the engine runs on a daemon thread instead.
- **Stdin on an executor thread hangs exit** (executor threads are joined); use a daemon thread.

## Overlay and OBS
- **Polling one request per frame managed ~30 fps** and looked choppy on stream: hence the
  `/frames` push stream (measured 59/60 fps). OBS must also run at 60 FPS.
- **A JS syntax error blanks the whole page** and Python tests can't see it:
  `test_page_script_is_valid_javascript` runs `node --check`.
- **Window Capture** went black on hybrid-GPU laptops and stops when minimized: the page draws
  the game itself from `pyboy.screen.ndarray` (a live view; copy with `tobytes()`).
- PyBoy samples are 0..127 (clamped, never negative): without the page's DC blocker it clicks.
- Twitch delay (2–4 s with Low Latency mode) is outside the bot; don't try to fix it in code.

## Tooling
- Network installs are blocked in Claude's sandbox: PyBoy isn't there, so backend tests use
  fakes, and anything with the real emulator needs the owner.
- Headless Chrome and Node are available in the sandbox: `pytest -m browser`,
  `python tools/overlay_check.py`.
