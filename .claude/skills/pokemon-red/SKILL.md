---
name: pokemon-red
description: Game-specific knowledge for running Pokémon Red on TwitchPlayerAgent the way the original 2014 Twitch Plays Pokémon did - the Season 1 rules and why, config values, ROM and PyBoy setup, input timing, AI-mode game notes, and streaming. Use with the twitchplayeragent-core skill when building, tuning or debugging the Pokémon Red setup, or as the template for adding another game.
---

# Pokémon Red on TwitchPlayerAgent

The core is game-agnostic. Everything Pokémon-specific is config values, the
`ai_notes` text, and this file. Read `twitchplayeragent-core` for the engine.

## The original rules (Twitch Plays Pokémon, Season 1, Feb 2014)
What the stream did, and how the bot matches it:
| Original | Here |
|---|---|
| Whole chat message = one button, case-insensitive | `parse_anarchy` |
| Buttons A, B, Up, Down, Left, Right, Start | `[game].buttons` default |
| Select removed after it was used to soft-reset | `select` left out of `buttons` |
| Anarchy: every input runs, in order | the shared queue, appended per message |
| Democracy (from Feb 18): votes tallied, most popular runs | `DemocracyTally`, one vote per user |
| Compound inputs in democracy: `start9`, `upleft` | `parse_democracy`, ≤ 9 presses |
| `wait` command in democracy | empty `Sequence`, presses nothing |
| Chat votes `anarchy` / `democracy` like buttons | `parse_mode_vote` |
| 80 % to enter democracy, 50 % to leave | `to_democracy = 0.8`, `to_anarchy = 0.5` |
Sources disagree on the democracy round length (reports say 10, 20 and 30 s); the default is
20 s. The meter's exact decay and the vote counting rules weren't documented: per-user latest vote,
60 s lifetime and `min_votes = 5` are this project's choices. Keep them configurable, not hardcoded.
`start9` was a famous protest vote, so keep it valid.

## Config for Pokémon Red
These are the defaults, so a fresh config only needs `[twitch].channel`:
```toml
[game]
name = "Pokemon Red"
buttons = ["a", "b", "up", "down", "left", "right", "start"]

[democracy]
window_seconds = 20
max_presses = 9

[meter]
to_democracy = 0.80
to_anarchy = 0.50
min_votes = 5        # set 1 to test the meter alone, restore before going live

[backend]
type = "pyboy"
hold_frames = 2
release_frames = 2

[backend.pyboy]
rom = "roms/pokemon_red.gb"
state_file = "saves/pokemon_red.state"
```

## ROM
- Never download or commit ROMs. The owner dumps their own cartridge with a USB dumper
  (GB Operator by Epilogue, or GBxCart RW by insideGadgets) and saves it as `roms/pokemon_red.gb`.
- `roms/` is gitignored, so it doesn't exist after a clone; the user creates it.
- Missing ROM → the backend exits with the path it looked for.

## PyBoy notes
- One press = button down for `hold_frames`, then up for `release_frames` (60 frames = 1 s).
  Red reads the joypad every frame; 2 + 2 is reliable. Raise `hold_frames` to 4 if presses are
  missed; lower `release_frames` if walking feels slow.
- One tap of a direction turns the player if facing elsewhere, otherwise moves one tile.
  Text boxes need A (or B) per page. Cancelling an evolution needs B pressed repeatedly.
- The game window takes keyboard focus when it opens. With `--stdin`, click back on the
  terminal before typing. `window_keyboard = false` (default) means keys typed into the window
  do nothing; PyBoy's own hotkeys would otherwise act (its `c` key cycles the palette, so
  Ctrl+C in the window recolours the game instead of quitting). Close the window or press
  Ctrl+C once in the terminal to save and quit; the bot reads the window events itself.
- Progress lives in `saves/pokemon_red.state` (autosave every 5 min and on exit), and is resumed
  on start. Delete that file to start a new game. PyBoy also keeps the cartridge save (`.ram`).
- Game window "Not Responding": check `saves/hang-report.txt` (empty = no freeze) for where it stuck.
- `[backend].type = "keyboard"` drives an external emulator instead (mGBA recommended). Match
  `[backend.keyboard.keys]` to its bindings (default A=x, B=z, Start=enter) and keep it focused.

## AI mode notes
`[game].ai_notes` (default `POKEMON_RED_AI_NOTES` in `config.py`) is the only game text the AI
gets. It says the game is the original Game Boy game, explains the tap semantics above, what A,
B and Start do, and example requests ("walk into the tall grass", "use thunderbolt", "run away").
The AI can't see the screen. It works from chat plus its previous one-line summary, so expect
it to follow explicit commands well and plain-English goals ("go to the Pokémon Center") only
roughly. Claude does this better than local models. Keep notes short and factual. If you add
detail, keep it to things the player must know about inputs, not walkthrough content.

## Streaming setup (OBS)
- One Browser Source, `http://localhost:8080`, 1920×1080: the game at an exact 7× scale with a
  thin bar underneath (mode, meter, votes or AI summary, latest inputs). The bar never covers the
  game, because Red's text boxes sit at the bottom. `?layout=sidebar` gives the original stream's
  right-hand input list instead.
- The game window can be minimized; the image comes from the emulator, not the window.
- Sound comes through the same Browser Source: tick "Control audio via OBS"; use Audio
  Monitoring "Monitor and Output" to hear it. The game window is muted to avoid double audio.
- Laptops: a mobile RTX 4090 has 16 GB VRAM, so for Ollama use `qwen3:14b` (9.3 GB), not
  `qwen3.5:27b`. NVENC encoding uses separate hardware and barely competes with the model.
- The bot reads chat directly, so stream delay doesn't add input lag. Viewers still see their
  input land late because of the video delay; that lag was part of the original's chaos.

## Testing Pokémon Red
1. `pytest`, then `python -m twitchplayeragent --stdin --dry-run < examples/chat.txt`.
2. With the ROM: `python -m twitchplayeragent --stdin`, type `start`, `a` in the terminal; each
   shows `PRESS …` and the game reacts.
3. Live: set `[twitch].channel`, run with `-c config.toml`, type in `twitch.tv/popout/<channel>/chat`.
   The channel doesn't need to be live.

## Adding another game later
Copy this pattern: choose `buttons` from the core's eight, write `ai_notes`, set the ROM and
state paths, and add a `<game>/SKILL.md` like this one (rules, config, setup, timing, AI notes,
testing). Nothing in the core should change. If a game needs more than Game Boy buttons, that's
a core change; discuss it with the owner first. They want Pokémon kept simple.
