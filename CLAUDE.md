# TwitchPlayerAgent

Twitch chat plays Pokémon Red with the original Twitch Plays Pokémon rules (anarchy,
democracy, 80/50 mode meter), plus an optional AI mode (Claude or a local Ollama model).

Skills: `.claude/skills/twitchplayeragent-core/SKILL.md` (game-agnostic engine) and
`.claude/skills/pokemon-red/SKILL.md` (game knowledge). Read them before larger changes.

## Keep it simple
The owner asked not to overcomplicate the codebase. Nine modules in `twitchplayeragent/`,
four flags (`-c`, `--stdin`, `--dry-run`, `-v`). Prefer a config setting over a flag, a function
over a class, and editing an existing module over adding one. Game knowledge is config and
skill text, never core code.

## Keep the skills in sync
When behavior, a module, a config field or a gotcha changes, update the matching skill in the
same commit. `tests/test_skills.py` fails if a skill passes 200 lines or misses a module or
config field.

## Commands
- Tests: `python -m pytest` (~3 s; helpers in `tests/conftest.py`)
- Offline replay: `python -m twitchplayeragent --stdin --dry-run < examples/chat.txt`
- With the game: `python -m twitchplayeragent --stdin` (needs `roms/pokemon_red.gb`)
- Commit to `main` directly; the owner prefers that over pull requests.
