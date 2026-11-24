# TwitchPlayerAgent

Lets Twitch chat play games with the rules of the original 2014 *Twitch Plays Pokémon*:
**Pokémon Red** in a built-in emulator, or **GTA 6** on an Xbox through Remote Play. An optional
AI mode lets Claude or a local model read chat and play.

## How chat plays

A message counts only when the **whole message** is a command. Case and surrounding spaces don't
matter, and everything else is ordinary chat.

| Command | What it does |
|---|---|
| `a` `b` `up` `down` `left` `right` `start` | Press that button |
| `anarchy` / `democracy` | Vote on the input mode (works in either mode) |

`select` is off because the original run disabled it after people used it to soft-reset; turn it
back on in `[game].buttons`.

- **Anarchy** (default): every valid input is pressed, in the order it arrived. The queue is capped
  (`[anarchy].max_queue`) and drops the oldest when full, so the game doesn't fall minutes behind.
- **Democracy**: the most popular input wins each round, which opens on its first vote and lasts
  `[democracy].window_seconds` (20 s). Each viewer gets one vote per round (a newer message
  replaces it), and a tie goes to the input voted for first. Democracy also takes compound inputs:
  `up4` (up ×4, repeat 1–9), `upleft`, `up2left3`, `start9` (the famous protest vote) and `wait`
  (nothing this round), at most 9 presses in all; `upup` and `up2` are the same vote.
- **The meter**: each viewer's latest `anarchy`/`democracy` counts for 60 seconds. As on the
  original stream, **80 %** of live votes switch to democracy and **50 %** switch back, never on
  fewer than `min_votes` (5). Switching clears queued inputs; with no votes the meter drifts back to
  anarchy.

### Streamer commands
Type these in your own Twitch chat (you and your moderators only; viewers are ignored):

| Command | Does |
|---|---|
| `!mode anarchy` / `!mode democracy` | switch now, ignoring the meter (viewers can still vote it back) |
| `!mode ai` | hand control to the AI (once it's set up, see below) |
| `!ticker Your message` / `!ticker` | set / clear the scrolling message; it's kept when the bot restarts |

## Setup

Requires Python 3.11+. You supply your own ROM; ROMs, saves and `config.toml` are git-ignored.

```bash
pip install -e ".[pyboy]"            # built-in Game Boy emulator
cp config.example.toml config.toml   # set [twitch].channel; every setting is explained in it
mkdir roms && cp /path/to/your/pokemon_red.gb roms/pokemon_red.gb
python -m twitchplayeragent -c config.toml
```

Chat is read anonymously (no login; the bot never posts). The game autosaves every 5 minutes and
on exit and resumes from that save; close its window or press Ctrl+C to quit. To try it without
Twitch, run `python -m twitchplayeragent --stdin --dry-run` and type `up`, `ash: a` or `democracy`.

Instead of PyBoy, `[backend].type = "keyboard"` sends keys to an external emulator such as mGBA,
like the 2014 stream (`pip install -e ".[keyboard]"`, keep the emulator focused and match
`[backend.keyboard.keys]` to its bindings), and `"log"` only logs presses (what `--dry-run` uses).

## Streaming with OBS
While the bot runs, **http://localhost:8080** is the whole stream layout: the game, with a thin bar
below showing the mode, the meter, the votes and countdown (or the AI's summary) and the latest
inputs. `http://localhost:8080/?layout=sidebar` gives the original stream's input list on the right.

1. In OBS, add **Sources → + → Browser**: URL `http://localhost:8080`, width **1920**, height
   **1080**, remove the default custom CSS, and tick **Control audio via OBS**.
2. That's the whole scene, sound included. The picture comes straight from the emulator, so you can
   minimize the game window, and the window itself is muted so Desktop Audio doesn't record it
   twice. To hear the game yourself, set the source's **Audio Monitoring** to *Monitor and Output*.
3. For a smooth stream, set OBS to 60 FPS. Twitch's **Low latency** mode keeps the delay at 2–4 s.

`[overlay].ticker` sets a message that scrolls along the bottom (`!ticker` changes it live).
Opening the page in a normal browser needs one click to start the sound. With the `keyboard`
backend the game area stays transparent, so put a Window Capture of your emulator underneath. If
port 8080 is taken, set `[overlay].port`.

## AI mode (optional)
`!mode ai` (or `[ai].enabled = true` to start in it) hands control to an AI. Every 10 seconds it
reads that window's chat, commands like `up2left` or plain English like "go heal at the Pokémon
Center", and picks up to 9 presses. It can only press the game's commands, each decision replaces
presses still waiting from the last, a quiet window leaves the game alone, and the overlay shows
what it's doing. Choose it with `provider`:

- **`"claude"`** (the best decisions): `pip install -e ".[claude]"` and set `ANTHROPIC_API_KEY`
  (`set ANTHROPIC_API_KEY=sk-ant-...` on Windows, `export` on Mac/Linux). API usage is billed
  separately from a claude.ai subscription; the default model, `claude-haiku-5-5`, is the cheapest.
- **`"ollama"`** (free, on your own GPU): install [Ollama](https://ollama.com), then
  `ollama pull qwen3.5:27b` (17 GB; fits a 24 GB card such as an RTX 4090). Smaller cards can set
  `model = "qwen3:14b"`.

## GTA 6 on Xbox
GTA 6 is console-only, so the bot becomes a virtual Xbox controller and **Xbox Remote Play** in the
Xbox app on your PC forwards it to the console like a controller plugged into the PC.

1. On the Xbox: **Settings → Devices & connections → Remote features → Enable remote features**.
2. On the PC: `pip install -e ".[gamepad]"`, accepting the ViGEmBus driver installer it runs.
3. **Start the bot first**, with the game file layered on your config (it keeps your channel and
   overlay): `python -m twitchplayeragent -c config.toml -c games/gta6.toml`
4. **Then start the Xbox app.** It only looks for controllers when it starts, so if it was already
   open, quit it completely (tray icon → Exit, or end "Xbox" in Task Manager) and reopen it.
5. Connect to your Xbox with Remote Play and start GTA 6 in story mode with the **Default** control
   scheme. Keep the Remote Play window in front while streaming.
6. In OBS, put a Window Capture of the Xbox app (or an HDMI capture card) under the Browser Source;
   the area above the overlay's bar is transparent.

Chat keeps the Twitch Plays Pokémon words: `up` `down` `left` `right` move briefly, `a` shoots and
`b` toggles aim. `goup`, `sprint`, `drive` and `reverse` stay on until `stop`, plus `jump` `crouch`
`cover` `melee` `enter` `holster` `handbrake` and `lookleft`/`lookright`/`lookup`/`lookdown`/
`lookback`. Every command and its timing is in `games/gta6.toml`.

## Development
```bash
pip install -e ".[dev]"
pytest                          # ~2 s: every module, both games replayed offline, docs in sync
pytest -m browser               # the overlay in Chrome: 60 fps, sound, no JS errors (needs Playwright)
python tools/overlay_check.py   # the same, plus screenshots in overlay-shots/
```

The design notes and module map are Claude skills in `.claude/skills/`: `twitchplayeragent-core`
(the engine), `pokemon-red` and `gta6-xbox` (the games).
