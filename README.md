# TwitchPlayerAgent

Lets Twitch chat play games. The first target is **Pokémon Red**, with the
message format and rules of the original 2014 *Twitch Plays Pokémon*.

## How chat plays

A message counts only when the **whole message** is a command. Case and
surrounding spaces don't matter. Everything else is ordinary chat.

| Command | What it does |
|---|---|
| `a` `b` `up` `down` `left` `right` `start` | Press that button |
| `anarchy` / `democracy` | Vote on the input mode (works in either mode) |

`select` is off by default because the original run disabled it after people
used it to soft-reset. You can turn it back on in `[game].buttons`.

### Anarchy (default)
Every valid input is pressed, in the order it arrived. This is the classic mode.
The queue is capped (`[anarchy].max_queue`). When it is full, the oldest
inputs are dropped so the game doesn't fall minutes behind chat.

### Democracy
Chat votes, and the most popular input wins each round. A round opens on its
first vote and lasts `[democracy].window_seconds` (default 20s). Each viewer
gets one vote per round, and if they send another message the newer one
replaces it. If two inputs tie, the one voted for first wins. Democracy also
accepts compound inputs:

| Input | Presses |
|---|---|
| `up4` | up ×4 (repeat count 1–9) |
| `upleft` | up, then left |
| `up2left3` | up, up, left, left, left |
| `start9` | start ×9 (the famous protest vote) |
| `wait` | nothing this round |

`upup` and `up2` count as the same vote. One input can be at most 9 presses in total.

### The anarchy/democracy meter
Each viewer's most recent `anarchy` or `democracy` message counts for 60 seconds.
The meter uses the original stream's asymmetric thresholds:

- **80%** of live votes are needed to switch anarchy to democracy
- **50%** of live votes are enough to switch back to anarchy

Switching mode clears any queued inputs. When nobody is voting, the meter
drifts back to anarchy. `min_votes` (default 5) stops one or two viewers
flipping the mode on a quiet stream.

### Streamer commands
Type these in your own Twitch chat (you and your moderators only; viewers are ignored):

| Command | Does |
|---|---|
| `!mode anarchy` / `!mode democracy` | switch now, ignoring the vote meter (viewers can still vote it back) |
| `!mode ai` | hand control to the AI (needs AI mode set up, see below) |
| `!ticker Your message` / `!ticker` | set / clear the scrolling message |

### AI mode (optional)
With `[ai] enabled = true`, an AI plays instead of anarchy and democracy.
Every 10 seconds (`window_seconds`), it reads all of that window's chat. Chat
can be commands like `up2left` or plain English like "go heal at the Pokémon
Center". The AI then picks up to 9 presses (`max_presses`).

- It can only press the game's allowed buttons.
- Each new decision replaces any presses still waiting from the last one.
- A window with no chat leaves the game alone.
- The overlay shows what the AI is doing in place of the meter.

Choose the AI with `provider`:

**`provider = "claude"`** uses Anthropic's API. It makes the best decisions.
```bash
pip install -e ".[claude]"
set ANTHROPIC_API_KEY=sk-ant-...    # Mac/Linux: export ANTHROPIC_API_KEY=sk-ant-...
```
API usage is billed separately from a claude.ai subscription. The default
model is `claude-haiku-5-5`, the cheapest; set `model` to use a stronger one.

**`provider = "ollama"`** uses a local model, which is free and runs on your
own GPU. Install [Ollama](https://ollama.com), then:
```bash
ollama pull qwen3.5:27b    # 17 GB; fits a 24 GB card such as an RTX 4090
```
Smaller cards can set `model = "qwen3:8b"`. No extra Python packages are
needed. Ollama holds the answer to the allowed buttons while generating it.

## Setup

Requires Python 3.11+.

```bash
pip install -e ".[pyboy]"          # built-in Game Boy emulator (recommended)
cp config.example.toml config.toml # then set [twitch].channel
mkdir roms && cp /path/to/your/pokemon_red.gb roms/pokemon_red.gb
python -m twitchplayeragent -c config.toml
```

You need to supply your own ROM. ROMs, saves and `config.toml` are git-ignored.

### Backends (`[backend].type`)
- **`pyboy`** (default): runs Pokémon Red inside [PyBoy](https://github.com/Baekalfen/PyBoy)
  and presses buttons on exact frames. Close the window to quit. It autosaves
  every 5 minutes and on exit, and resumes from that save on the next start.
- **`keyboard`**: sends keypresses to an external emulator (mGBA,
  VisualBoyAdvance, BizHawk), which is how the 2014 stream worked. Keep the
  emulator window focused and match `[backend.keyboard.keys]` to its bindings.
  Install it with `pip install -e ".[keyboard]"`.
- **`log`**: dry run that only logs presses (`--dry-run`).

### Try it without Twitch
```bash
python -m twitchplayeragent --stdin --dry-run
ash: up
misty: democracy
```

### Streaming with OBS
While the bot runs, it serves the whole stream layout at **http://localhost:8080**:
the game, with a thin bar underneath showing the mode, the anarchy/democracy
meter, the democracy votes and countdown (or the AI's summary), and the latest
inputs. For the original stream's look, with a tall input list on the right, use
`http://localhost:8080/?layout=sidebar` instead.

1. Start the bot.
2. In OBS, add **Sources → + → Browser**, set URL `http://localhost:8080`,
   width **1920** and height **1080**, and remove the default custom CSS.
3. That's the whole scene. The game image comes straight from the emulator, so
   you can **minimize the game window**. Window Capture isn't needed, and
   neither are its laptop black-screen fixes.

**Scrolling message:** set `ticker = "..."` under `[overlay]` for a message that scrolls
along the bottom of the stream. Change it live by typing `!ticker Your new message` in your
own Twitch chat (from your phone works too); `!ticker` on its own clears it. Only you and
your moderators can change it, and the latest message is kept when the bot restarts.

**Sound comes through the same Browser Source.** Tick **Control audio via
OBS** in its properties, and the game shows up in OBS's audio mixer like any
other source. The game window is muted, so Desktop Audio won't capture it a
second time. To hear the game yourself, set that source's **Audio Monitoring**
to *Monitor and Output*. Set `[overlay].audio = false` to go back to sound from
the game window.

Open the same address in any browser to preview it (click the page once to
start sound; browsers block autoplay, OBS doesn't). With the `keyboard` backend
there's no built-in game image or sound: the left side stays transparent, so put
a Window Capture of your emulator underneath. If port 8080 is taken, set
`[overlay].port`.

## GTA 6 on Xbox
GTA 6 is console-only, so the bot reaches your Xbox through **Xbox Remote Play**
in the Xbox app on your PC. The bot becomes a virtual Xbox controller, and the
Xbox app forwards it to the console like a controller plugged into the PC.

1. On the Xbox: **Settings → Devices & connections → Remote features → Enable
   remote features**.
2. On the PC: `pip install -e ".[gamepad]"`. This also runs the ViGEmBus driver
   installer; accept it.
3. **Start the bot first**, with your usual config plus the game file (which keeps
   your channel and overlay):
   ```bash
   python -m twitchplayeragent -c config.toml -c games/gta6.toml
   ```
4. **Then start the Xbox app.** It only looks for controllers when it starts, so if
   it was already open, quit it completely (tray icon → Exit, or end "Xbox" in Task
   Manager) and reopen it. Closing the Remote Play window isn't enough.
5. Connect to your Xbox with Remote Play and start GTA 6 in story mode, with the
   **Default** control scheme. Keep the Remote Play window in front while streaming.

Chat commands keep the Twitch Plays Pokémon words: `up` `down` `left` `right`
move briefly, `a` shoots and `b` toggles aim. `goup`, `sprint`, `drive` and
`reverse` stay on until `stop`, plus `jump` `crouch` `cover` `melee` `enter`
`holster` `handbrake` and `lookleft`/`lookright`/`lookup`/`lookdown`/`lookback`.
The full list is in `games/gta6.toml`.

In OBS, put a Window Capture of the Xbox app (or an HDMI capture card) under the
Browser Source. The overlay's bar sits along the bottom, and the area above it
is transparent.

## Chat connection
Chat is read anonymously over Twitch IRC (TLS, port 6697), so no login is
needed; the bot never posts. It reconnects automatically if the connection
drops.

## Development
```bash
pip install -e ".[dev]"
pytest                    # ~5 s, no game or network needed
pytest -m browser         # overlay in Chrome: 60 fps, sound, no JS errors (needs Playwright)
python tools/overlay_check.py                                     # same, plus screenshots in overlay-shots/
python -m twitchplayeragent --stdin --dry-run < examples/chat.txt  # offline replay
```

| File | Role |
|---|---|
| `commands.py` | chat text → button / compound input / mode vote |
| `modes.py` | anarchy/democracy meter and democracy vote tally |
| `engine.py` | decision logic and one input queue for every mode |
| `llm.py` | AI mode (Claude or Ollama) |
| `chat.py` | Twitch IRC and terminal chat sources |
| `backends.py` | PyBoy, keyboard and dry-run input |
| `overlay.py` / `overlay.html` | local web server / the OBS page itself |
| `config.py` / `__main__.py` | TOML config and command line |

Tests: one file per module, `tests/test_<module>.py`. Claude skills in `.claude/skills/`:
`twitchplayeragent-core` (a short map, with details in `references/` read only when needed)
and `pokemon-red` (game knowledge).
