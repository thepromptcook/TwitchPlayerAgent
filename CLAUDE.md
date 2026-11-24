# TwitchPlayerAgent

Twitch chat plays Pokémon Red (PyBoy) and GTA VI (an Xbox through Remote Play) with the original
Twitch Plays Pokémon rules, plus an optional AI mode (Claude or Ollama), streamed through one OBS
Browser Source. Work in this repo, not TwitchPlaysTest, unless the owner says otherwise.

Start from the `twitchplayeragent-core` skill (`.claude/skills/twitchplayeragent-core/SKILL.md`:
module map, principles, workflow), then read only the reference for the area you change. Game
knowledge is in the `pokemon-red` and `gta6-xbox` skills.

## The owner's rules
- Keep it simple: no new modules or flags without a real need, config over flags, and a game is a
  `games/` file plus a skill, never core code.
- Run `python -m pytest` (~2 s) after every change, and commit straight to `main` (no pull requests).
- Update the matching skill, `config.example.toml` or README in the same commit as the change;
  `tests/test_docs.py` fails when they drift.
- Tell the owner only the steps a change needs (usually `git pull` and restart the bot; a reinstall
  only when `pyproject.toml` dependencies change).
