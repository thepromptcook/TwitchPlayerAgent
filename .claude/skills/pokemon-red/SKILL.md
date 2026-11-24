---
name: pokemon-red
description: Game knowledge for running Pokémon Red on TwitchPlayerAgent the way the original 2014 Twitch Plays Pokémon did - Season 1 rules and why, ROM and PyBoy setup, input timing, AI-mode game notes, and the OBS/Twitch streaming setup. Use with twitchplayeragent-core when tuning, streaming or debugging Pokémon Red, or as the template for adding another game.
---

# Pokémon Red on TwitchPlayerAgent

Everything Pokémon-specific is config defaults, `[game].ai_notes`, and this file. The engine
is in `twitchplayeragent-core`. A fresh config only needs `[twitch].channel`.

## The original rules (Twitch Plays Pokémon, Season 1, Feb 2014)
| Original | Here |
|---|---|
| Whole chat message = one button, case-insensitive | `parse_anarchy` |
| A, B, Up, Down, Left, Right, Start | `[game].buttons` default |
| Select removed after it was used to soft-reset | `select` left out of `buttons` |
| Anarchy: every input runs, in order | the queue, appended per message |
| Democracy (from Feb 18): votes tallied, most popular runs | `DemocracyTally`, one vote per user |
| Compound inputs: `start9`, `upleft`; a `wait` command | `parse_democracy`, ≤ 9 presses |
| Chat votes `anarchy` / `democracy` like buttons | `parse_mode_vote` |
| 80 % to enter democracy, 50 % to leave | `to_democracy = 0.8`, `to_anarchy = 0.5` |
Undocumented in the sources, so this project's choices (keep them configurable): round length
20 s (reports say 10–30 s), per-user latest vote, 60 s vote lifetime, `min_votes = 5`.
`start9` was a famous protest vote: keep it valid.

## ROM and saves
- Never download or commit ROMs. The owner dumps their own cartridge (GB Operator, GBxCart RW)
  to `roms/pokemon_red.gb`; `roms/` is gitignored, so they create it after a clone.
- Progress: `saves/pokemon_red.state`, autosaved every 5 min and on exit, resumed on start.
  Delete it to start over. PyBoy also keeps the cartridge save (`.ram`).

## Input timing
- One press = down `hold_frames` (2), up `release_frames` (2), at 60 frames/s. Red reads the
  joypad every frame. Raise `hold_frames` to 4 if presses go missing; lower `release_frames` if
  walking feels slow.
- One direction tap turns the player if facing elsewhere, else moves one tile. Text boxes need
  A (or B) per page. Cancelling an evolution needs repeated B.

## AI mode notes
`[game].ai_notes` (default `POKEMON_RED_AI_NOTES` in `config.py`) is the only game text the AI
gets: original Game Boy game, tap semantics, what A, B and Start do, example requests ("walk into
the tall grass", "use thunderbolt", "run away"). The AI can't see the screen, so it follows
explicit commands well and plain-English goals only roughly; Claude does better than local
models. Keep notes short, about inputs, not walkthrough content.

## Streaming (OBS + Twitch)
- One Browser Source: `http://localhost:8080`, 1920×1080, "Control audio via OBS" ticked. It
  carries picture (game at an exact 7× scale, thin bar below so Red's bottom text boxes stay
  visible) and sound. The PyBoy window can be minimized. `?layout=sidebar` = the original's
  right-hand input list.
- OBS: Video 60 FPS (30 halves the game's frames), NVENC, ~6000 Kbps, keyframe interval 2,
  Stream Delay off. Twitch: Creator Dashboard → Settings → Stream → Low latency (2–4 s delay).
- To hear the game while streaming: Audio Monitoring "Monitor and Output" on the source.
- Phone control: an OBS WebSocket remote (OBS Blade on Android), and Claude working on the PC
  through the Claude desktop app with the repo folder connected.
- `type = "keyboard"` with mGBA works too, but mGBA must keep keyboard focus and needs Window
  Capture plus Application Audio Capture; PyBoy is the convenient default.

## Testing on the owner's PC
1. `python -m twitchplayeragent -c config.toml --stdin`: type `start`, `a` in the terminal;
   each shows `PRESS …` and the game reacts. Check `http://localhost:8080` in a browser.
2. Live: run without `--stdin`, type in `twitch.tv/popout/<channel>/chat` (works offline too).
3. Window freezes: `saves/hang-report.txt` (empty = no freeze) shows where it stuck.

## Adding another game later
Pick `buttons` from the core's eight, write `ai_notes`, set ROM and state paths, add a
`<game>/SKILL.md` like this one. Nothing in the core should change; a game needing more than
Game Boy buttons is a core change to discuss with the owner first.
