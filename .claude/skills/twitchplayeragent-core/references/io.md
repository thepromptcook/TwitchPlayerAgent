# I/O: chat, backends, overlay, CLI

## Chat (`chat.py`)
- `TwitchIrcChat`: TLS `irc.chat.twitch.tv:6697`, anonymous `NICK justinfan<5 digits>` (no
  login; the bot never posts). `CAP REQ :twitch.tv/tags twitch.tv/commands`, `JOIN #channel`,
  `PING` → `PONG`, `RECONNECT`/EOF → reconnect with backoff 1→60 s.
- `parse_irc_line`: optional `@tags`, login from the prefix (lowercased, the vote identity),
  `display-name` tag for the overlay, text after ` :`.
- `StdinChat`: `user: text` lines (bare text is user `you`), skips blank and `#` lines; reads
  stdin on a daemon thread (see gotchas).

## Backends (`backends.py`)
`press(button)` blocks until pressed *and* released, one at a time. Hooks set by
`__main__`: `on_frame(w, h, rgba)` and `on_audio(rate, samples)` → the overlay.
- `PyBoyBackend` (default, `needs_main_thread`): `_open` creates PyBoy (`no_input`,
  `sound_volume` 0 when the overlay has sound, real-time speed) and loads `state_file`. The loop:
  take a `(button, Event)` job → `button_press`, tick `hold_frames`, `button_release`, tick to
  hold+release, set the Event. Every frame: `_window_pump()` (quit → stop) and `_publish`
  (frame + sound). Once a second: re-arm the freeze watchdog (`faulthandler` → `hang-report.txt`
  beside the save) and autosave every `autosave_minutes` (tmp + replace). On exit: save, stop.
- `GamepadBackend`: virtual Xbox 360 controller via vgamepad (`VX360Gamepad`; buttons through
  `XUSB`, triggers and sticks as floats, `update()` sends). State = toggled buttons + toggled
  stick positions; a momentary command applies on top for `seconds`, then the toggled state is
  re-sent; a toggle flips (a new direction on the same stick replaces the old); `release` clears.
  `stop()` resets the pad. Windows only; Xbox Remote Play forwards it to a console.
- `KeyboardBackend`: keys into a focused external emulator (mGBA); `pydirectinput` on Windows,
  else `pynput`; `keys` map, `hold_ms`, `gap_ms`. No picture or sound for the overlay.
- `LogBackend`: records `pressed`; `--dry-run` selects it.
- Tests drive `run_main_loop` with a fake `pyboy` module and a fake `sdl2`.

## Overlay (`overlay.py`, page in `overlay.html`)
One OBS Browser Source, `http://localhost:<port>` at 1920×1080, 127.0.0.1 only.
- Routes: `/` the page (`const AUDIO = false;` swapped in when `audio` is off); `/state`
  `Engine.overlay_state` JSON, polled every 250 ms; `/frames` one long HTTP/1.0 response pushing
  every frame as `<HH` width,height + RGBA (a `Condition` wakes each stream on `set_frame`);
  `/audio?after=N` chunks newer than N with `X-Seq`/`X-Rate` (a new or lagging listener gets
  the last 3); `/favicon.ico` 204.
- Page layouts (`?layout=`): default `bar`, the game at exactly 7× (1120×1008) centred with a
  72 px bar **below** it (never over: Pokémon text boxes are at the bottom) showing mode, meter,
  one-line votes or AI summary, and newest inputs fading at the right edge. `sidebar`: game
  1200×1080 left, 720 px panel right. Canvas `image-rendering: pixelated`, hidden (transparent)
  when no frames arrive. Chat text only via `textContent`.
- Sound in the page: Web Audio, a DC blocker (`y = x - x₁ + 0.995·y₁`) because PyBoy samples
  are 0..127, buffers scheduled ~0.12 s ahead with resync on under/overrun. OBS autoplays;
  normal browsers need one click.
- Busy port → SystemExit naming `[overlay].port`; port 0 picks a free one (tests).

## CLI (`__main__.py`)
Loads config (`-c` repeatable, merged in order), `--dry-run` forces the log backend, checks `unavailable()` in AI mode, wires the
overlay hooks, runs the engine on a daemon thread while PyBoy owns the main thread (SDL needs
it on macOS). Logging goes through `QueueHandler` → `QueueListener` so a log call never blocks.
Windows: `disable_quick_edit()`; `stop_on_ctrl_c(stop)` is the SIGINT handler (first press:
save and quit; second: force).
