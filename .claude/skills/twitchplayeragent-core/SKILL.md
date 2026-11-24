---
name: twitchplayeragent-core
description: TwitchPlayerAgent's game-agnostic core - Twitch chat to game input with the original Twitch Plays Pokémon rules, an optional AI mode (Claude or Ollama), PyBoy/keyboard/virtual-Xbox backends and a one-source OBS overlay. Module map, specs, past bugs and workflow; use to change, debug or rebuild any part. Game knowledge is in pokemon-red and gta6-xbox.
---

# TwitchPlayerAgent core

Twitch chat → `commands` parse → `engine` (anarchy / democracy / AI) → one press queue → a backend
presses → the overlay page shows game, sound and inputs to OBS. Python ≥ 3.11; the core is
standard library only (extras: `pyboy`, `keyboard`, `gamepad`, `claude`, `dev`).

## Principles
- Simple, as the owner asked: nine modules plus `overlay.html`, four flags (`-c` repeatable,
  `--stdin`, `--dry-run`, `-v`); config over flags, functions over classes, existing modules over
  new ones.
- Games are data: `[game]` config or a `games/<game>.toml` layered with `-c config.toml -c
  games/<game>.toml`, plus a skill; never core code.
- Decision logic is synchronous and takes `now`, so tests need no asyncio, game or network.
- Config mistakes are errors that name the section and the fix.

## Modules (`twitchplayeragent/`)
| File | Role | Spec |
|---|---|---|
| `commands.py` | chat text → command, compound input, mode vote | [rules](references/rules.md) |
| `modes.py` | `ModeMeter` (80/50 switch), `DemocracyTally` | [rules](references/rules.md) |
| `engine.py` | `Engine`: `handle`, `tick`, `force_mode`, `set_ticker`, `apply_ai`, `overlay_state`, `run` | [rules](references/rules.md) |
| `llm.py` | AI mode: `Planner`, prompt, Claude and Ollama calls, `unavailable` | [ai](references/ai.md) |
| `chat.py` | `TwitchIrcChat` (anonymous IRC), `StdinChat` | [io](references/io.md) |
| `backends.py` | `PyBoyBackend`, `KeyboardBackend`, `GamepadBackend`, `LogBackend` | [io](references/io.md) |
| `overlay.py` + `overlay.html` | local web server + the OBS page | [io](references/io.md) |
| `__main__.py` | CLI, threads, logging, Ctrl+C | [io](references/io.md) |
| `config.py` | TOML → dataclasses, layering, validation | below |

[io](references/io.md) also records the bugs already found (most only showed on Windows or in OBS):
read it before touching PyBoy, Windows behavior, OBS or the page, and don't undo those fixes.

## Config (`config.py`)
- `config.example.toml` explains every field at its default; `tests/test_docs.py` fails when it
  and the dataclasses differ, so change both together.
- `load_config([a, b])` deep-merges TOML files in order (later wins; `[game.commands]` replaced
  whole), builds the nested dataclasses (unknown keys name their section) and `validate()`s.
  A missing file or TOML syntax error names the file and line, with hints for unquoted text and
  curly quotes.
- Controller games: `[game.commands]` entries (`check_command`; fields at the top of
  `games/gta6.toml`) replace `[game].buttons` as the vocabulary (`Config.allowed_commands`) and
  need backend `gamepad` (or `log`). `PAD_BUTTONS` maps their button names to vgamepad's.
- Renaming or removing a field breaks the owner's `config.toml`: tell them which line to change.

## Workflow
- `grep -n` first and read only what you change; skip `overlay.html` for Python work.
- `python -m pytest` (~2 s) checks all that needs no Windows: one test file per module (helpers
  `msg`, `make_cfg`, `gta_cfg`, `drain` in `tests/conftest.py`), both games replayed offline
  through the real CLI (`test_offline_replay`), and the docs (`test_docs.py`: skills under 200
  lines with working links and every module, the example config, every game file).
- Overlay page changes: `pytest -m browser` (fps, sound, JS errors) or
  `python tools/overlay_check.py` (the same, plus screenshots in `overlay-shots/`).
- A new game: a `games/<game>.toml` (or `[game]` defaults for a Game Boy game) and a skill like
  `pokemon-red` or `gta6-xbox`; the tests load every game file and look for its skill.
- Only the owner can check Windows, real PyBoy, OBS, Twitch and the Xbox: give the fewest steps
  (usually `git pull` and restart the bot) and ask for the terminal output or
  `saves/hang-report.txt`.

## Rebuild order
`commands` → `modes` → `config` → `engine` (sync logic + tests) → `backends` (`LogBackend` first)
→ `chat` → `overlay` → `__main__` → `llm` (fake Claude client, fake Ollama `http.server`).
