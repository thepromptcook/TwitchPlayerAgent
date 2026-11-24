# I/O: chat, backends, overlay, CLI, and the bugs already found

Most of these bugs looked fine in Linux tests and only showed on the owner's Windows PC or in OBS.
Don't undo the fixes.

## Chat (`chat.py`)
- `TwitchIrcChat`: TLS `irc.chat.twitch.tv:6697`, anonymous `NICK justinfan<5 digits>` (no login;
  the bot never posts), `CAP REQ :twitch.tv/tags twitch.tv/commands`, `JOIN #channel`, `PING` →
  `PONG`, `RECONNECT` or EOF → reconnect with backoff 1 → 60 s.
- `parse_irc_line`: optional `@tags`; the login from the prefix (lowercased: the vote identity),
  `display-name` for the overlay, `mod` = moderator or broadcaster, the text after ` :`.
- `StdinChat`: `user: text` lines (bare text is `you`; all count as moderator), skips blank and `#`
  lines. It reads stdin on a daemon thread: an executor thread is joined at exit and hung it.

## Backends (`backends.py`)
`press(command)` blocks until pressed and released, one at a time, on a worker thread. `__main__`
points `on_frame(w, h, rgba)` and `on_audio(rate, samples)` at the overlay.
- `PyBoyBackend` (default) owns the main thread (`needs_main_thread`; SDL windows need it on
  macOS), so the engine runs on a daemon thread. `_open`: PyBoy at real-time speed, `state_file`
  loaded, `no_input` (typed keys played, and Ctrl+C's `c` cycled the palette) and `sound_volume`
  0 when the overlay carries sound (it scales only the window's playback, not `pyboy.sound`, so
  Desktop Audio doesn't double it). Loop: a `(command, Event)` job → `button_press`, tick
  `hold_frames`, `button_release`, tick to hold + release, set the Event. Every frame
  `_window_pump()` reads and drops SDL events and stops on `SDL_QUIT` (`no_input` stops PyBoy
  reading them, and the window went "Not Responding" with close and Ctrl+C lost), and `_publish`
  sends `pyboy.screen.ndarray` (a live view: copy with `tobytes()`) and the frame's samples. Once a
  second: re-arm `faulthandler` (stacks to `hang-report.txt` beside the save after a 10 s stall)
  and autosave every `autosave_minutes` (tmp + replace). On exit: save, stop.
- `GamepadBackend`: a vgamepad `VX360Gamepad` (Windows, ViGEmBus; retired upstream but still
  installs). Toggled buttons and stick positions persist; a momentary command applies on top for
  `seconds`, then the toggled state is re-sent; a toggle flips (a new direction on the same stick
  replaces the old); `release` clears; `stop()` resets the pad. Xbox Remote Play forwards it to a
  console, but the Xbox app only finds controllers when it starts (see `gta6-xbox`).
- `KeyboardBackend`: keys into a focused external emulator (mGBA): `pydirectinput` on Windows
  (emulators ignore virtual keys), else `pynput`. No picture or sound for the overlay.
- `LogBackend`: records `pressed`; `--dry-run` uses it.

## Overlay (`overlay.py`, page `overlay.html`)
One OBS Browser Source at 1920×1080, served on 127.0.0.1 only.
- Routes: `/` the page (`const AUDIO = false;` swapped in when `audio` is off); `/state` the
  `overlay_state` JSON, polled every 250 ms; `/frames` one long HTTP/1.0 response pushing every
  frame as `<HH` width, height + RGBA, a `Condition` waking each stream (polling once per frame
  managed ~30 fps and looked choppy on stream); `/audio?after=N` int8 stereo chunks newer than N
  with `X-Seq`/`X-Rate` (a new or lagging listener gets the last 3); `/favicon.ico` 204.
- Layouts (`?layout=`): `bar` (default) puts the game at exactly 7× (1120×1008) with a 72 px bar
  **below** it, never over (Pokémon's text boxes are at the bottom): mode, meter, one-line votes or
  AI summary, newest inputs fading at the right. `sidebar`: game 1200×1080, 720 px panel. The
  canvas is `image-rendering: pixelated` and transparent without frames (a Window Capture of a
  console shows through). Chat text only via `textContent`.
- Ticker: a 44 px strip at the very bottom while `state.ticker` is set (body class `ticker`); the
  game shrinks to keep 10:9 (bar 1071×964, sidebar 1151×1036). Two copies of the text slide left by
  half the track (CSS animation, ~120 px/s, restarted on change), so any length loops.
- Sound: Web Audio with a DC blocker (`y = x - x₁ + 0.995·y₁`: PyBoy samples are 0..127 and it
  clicked without), buffers scheduled ~0.12 s ahead, resync on under/overrun. OBS autoplays;
  browsers need a click.
- A busy port → SystemExit naming `[overlay].port`; port 0 picks a free one (tests).
  `SO_REUSEADDR` is off on Windows, where it let a second program share a busy port silently.
- A JS syntax error blanks the page and Python can't see it: `test_page_script_is_valid_javascript`
  runs `node --check`.
- Window Capture went black on hybrid-GPU laptops and stops when minimized, hence the page draws
  the game itself. OBS must run at 60 FPS (30 halved the game's frames). Twitch's delay (2–4 s
  with Low latency) is outside the bot. OBS Blade couldn't connect while OBS's "Enable WebSocket
  server" was off; it reaches the PC over Tailscale, and port 4455 is never exposed.

## CLI (`__main__.py`)
`-c` repeats (merged in order); `--dry-run` forces `log`; AI mode at start checks `unavailable()`
and exits with its one-line fix; overlay hooks wired; the engine on a daemon thread while PyBoy
owns the main thread. Windows fixes:
- A click in a QuickEdit console paused every program writing to it and froze the game:
  `disable_quick_edit()`, and logging through `QueueHandler` → `QueueListener`, so a log call never
  blocks. The queue handler gets `Formatter("%(message)s")`: `basicConfig`'s default printed every
  prefix twice.
- A `KeyboardInterrupt` inside PyBoy's Cython frame limiter is swallowed ("Exception ignored"), so
  Ctrl+C took many presses: `stop_on_ctrl_c` handles SIGINT (first: save and quit; second: force).

## Claude's sandbox
No network installs (no PyBoy, hence fake `pyboy`/`sdl2`/`vgamepad` modules in the tests), but
headless Chrome and Node are there for `pytest -m browser` and `node --check`.
