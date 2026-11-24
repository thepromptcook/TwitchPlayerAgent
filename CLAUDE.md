# TwitchPlayerAgent

Twitch chat plays Pokémon Red with the original Twitch Plays Pokémon rules (anarchy,
democracy, 80/50 mode meter), plus an optional AI mode (Claude or a local Ollama model),
streamed through one OBS Browser Source.

Start from `.claude/skills/twitchplayeragent-core/SKILL.md` (module map, workflow), then read
only the reference for the area you change. Game knowledge: `.claude/skills/pokemon-red/SKILL.md`.

## Keep it simple
The owner asked not to overcomplicate the codebase: nine modules plus `overlay.html`, four flags
(`-c`, `--stdin`, `--dry-run`, `-v`). Prefer a config setting over a flag, a function over a class,
and an existing module over a new one. Game knowledge is config and skill text, never core code.

## Work efficiently
- `grep -n` first, then read only what you change; don't open `overlay.html` for Python work.
- `python -m pytest` (~5 s, terse) after every change; `pytest -m browser` or
  `python tools/overlay_check.py` when the overlay page changes.
- Commit straight to `main`; the owner prefers that over pull requests.
- Tell the owner only the steps a change needs (usually `git pull` and restart the bot; a
  reinstall only when `pyproject.toml` dependencies change). Don't repeat the full setup.
- Windows, real PyBoy, OBS and Twitch can only be checked on the owner's PC: ask for the
  terminal output or `saves/hang-report.txt`.

## Keep the skills in sync
Update the matching skill file in the same commit as a behavior, module, config or gotcha
change. `tests/test_skills.py` fails if a skill file passes 200 lines, a reference link is
broken, or a module or config field is missing from the core skill.
