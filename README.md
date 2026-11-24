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

### Stream overlay (OBS)
The bot writes these files to `overlay/`. Add each one as a **Text** source
with **Read from file** turned on:

- `inputs.txt`: scrolling list of `user  input`
- `mode.txt`: current mode and the bar (`#` is the democracy share, `|` marks the line the other mode needs to reach)
- `democracy.txt`: live vote counts and countdown (empty during anarchy)

## Chat connection
Chat is read over Twitch IRC (TLS, port 6697). It connects anonymously by
default, which is enough because the bot never posts. It reconnects
automatically if the connection drops. The chat source is pluggable, so an
EventSub reader can be added later.

## Development
```bash
pip install -e ".[dev]"
pytest
```

Layout: `commands.py` (parsing), `modes.py` (meter and vote tally),
`engine.py` (decision loop), `chat.py`, `overlay.py`, and `backends/`.
