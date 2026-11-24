---
name: twitchplayeragent-core
description: Map of TwitchPlayerAgent's game-agnostic core - a Python bot that turns Twitch chat into game input with the original Twitch Plays Pokémon rules (anarchy, democracy, mode meter), an optional AI mode (Claude or local Ollama), PyBoy/keyboard/virtual-Xbox-controller backends and a one-source OBS overlay. Use to change, debug or rebuild any part of it; read only the reference file for the area you touch. Game knowledge is in the pokemon-red and gta6-xbox skills.
---

# TwitchPlayerAgent core

Twitch chat → `commands` parse → `engine` (anarchy / democracy / AI) → one press queue →
backend presses buttons → overlay page shows game, sound and inputs to OBS. The vocabulary is
the Game Boy buttons (Pokémon), or a controller game's `[game.commands]` table from a game file
layered with `-c config.toml -c games/<game>.toml` (GTA VI on Xbox).
Python ≥ 3.11, standard library only in the core. Optional extras: `pyboy`, `keyboard`,
`claude`, `dev`.

## Principles
- The owner wants it simple: few files, four flags (`-c`, `--stdin`, `--dry-run`, `-v`), config
  over flags, functions over classes, edit an existing module before adding one.
- Game knowledge is config (`[game]`, `games/<game>.toml`) and the game's skill, never core code.
- Decision logic is synchronous and takes `now`, so tests need no asyncio, game or network.
- Strict config: unknown keys are errors with a readable message.

## Modules (`twitchplayeragent/`)
| File | Role | Reference |
|---|---|---|
| `commands.py` | chat text → button, compound input, mode vote | [rules](references/rules.md) |
| `modes.py` | `ModeMeter` (80/50 switch), `DemocracyTally` | [rules](references/rules.md) |
| `engine.py` | `Engine`: `handle`, `tick`, `apply_ai`, `next_press`, `overlay_state`, `run` | [rules](references/rules.md) |
| `llm.py` | AI mode: `Planner`, prompt, Claude and Ollama calls | [ai](references/ai.md) |
| `chat.py` | `TwitchIrcChat` (anonymous IRC), `StdinChat` | [io](references/io.md) |
| `backends.py` | `PyBoyBackend`, `KeyboardBackend`, `GamepadBackend`, `LogBackend`, `make_backend` | [io](references/io.md) |
| `overlay.py` + `overlay.html` | local web server + the OBS page (picture, sound, bar) | [io](references/io.md) |
| `config.py` | TOML → dataclasses, layered `load_config`, `check_command` | [config](references/config.md) |
| `__main__.py` | CLI, threads, logging, Ctrl+C | [io](references/io.md) |

Read [gotchas](references/gotchas.md) before touching PyBoy, Windows behavior, OBS or the
overlay page: each entry is a bug the owner already hit.

## Fast, low-usage workflow
1. Find before reading: `grep -n` for the function, then read just that part. Skip
   `overlay.html` unless the page changes.
2. Test: `python -m pytest` (~5 s, terse). One file per module: `tests/test_<module>.py`;
   helpers `msg`, `make_cfg`, `drain` in `tests/conftest.py`.
3. Overlay page changes: `pytest -m browser` (fps, sound, JS errors) or
   `python tools/overlay_check.py` (also writes screenshots to `overlay-shots/`).
4. Offline end to end: `python -m twitchplayeragent --stdin --dry-run < examples/chat.txt`.
5. Commit to `main` with the matching skill update in the same commit.
6. Only the owner can verify Windows, real PyBoy with the ROM, OBS and Twitch. Give them the
   minimum steps (usually `git pull` and restart the bot) and ask for the terminal output or
   `saves/hang-report.txt` if something is off.

## Rebuild order
`commands` → `modes` → `config` → `engine` (sync logic + tests) → `backends` (LogBackend first)
→ `chat` → `overlay` → `__main__` → `llm` (fake Claude client, fake Ollama `http.server`).
