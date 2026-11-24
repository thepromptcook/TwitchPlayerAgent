---
name: pokemon-red
description: Pokémon Red on TwitchPlayerAgent the way the 2014 Twitch Plays Pokémon ran it - the Season 1 rules and why, ROM and saves, input timing, AI-mode notes, streaming. Use with twitchplayeragent-core when tuning, streaming or debugging Pokémon Red, or as the template for another Game Boy game.
---

# Pokémon Red

Pokémon Red is the config defaults (`[game]`, `[backend.pyboy]`; see `config.example.toml`) plus
this file; the engine is in `twitchplayeragent-core`, the owner's steps in `README.md`.

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

The sources don't say, so these are this project's choices (keep them configurable): 20 s rounds
(reports say 10–30 s), each user's latest vote, a 60 s vote lifetime, `min_votes = 5`. `start9`
was a famous protest vote: keep it valid.

## ROM and saves
- Never download or commit ROMs. The owner dumps their own cartridge (GB Operator, GBxCart RW) to
  `roms/pokemon_red.gb`; `roms/` is gitignored, so it's created after a clone.
- `saves/pokemon_red.state`: autosaved every 5 min and on exit, resumed on start; delete it to start
  over. PyBoy also keeps the cartridge save (`.ram`).

## Input timing
- One press is down `hold_frames` (2) then up `release_frames` (2) at 60 frames/s; Red reads the
  joypad every frame. Raise `hold_frames` to 4 if presses go missing; lower `release_frames` if
  walking feels slow.
- A direction tap turns the player if facing elsewhere, else moves one tile. Text boxes need A (or
  B) per page; cancelling an evolution needs repeated B.

## AI mode
`[game].ai_notes` (the default in `config.py`) is the only game text the AI gets: the original Game
Boy game, tap semantics, what A, B and Start do, example requests. The AI can't see the screen, so
it follows explicit commands well and plain-English goals only roughly; Claude does better than
local models. Keep the notes about inputs, not walkthrough content.

## Streaming
- The owner's OBS steps are in the README (one Browser Source carries picture and sound; the PyBoy
  window can be minimized). Settings that fixed choppy video: OBS at 60 FPS, NVENC ~6000 Kbps,
  keyframe interval 2. Twitch Low latency mode keeps the delay at 2–4 s.
- Phone control: OBS Blade over Tailscale, and Claude on the PC through the Claude desktop app with
  the repo folder connected.
- mGBA (`type = "keyboard"`) works too but needs keyboard focus, Window Capture and Application Audio
  Capture; PyBoy is the convenient default.

## Checking on the owner's PC
1. `python -m twitchplayeragent -c config.toml --stdin`: type `start`, `a`; each shows `PRESS …`
   and the game reacts; `http://localhost:8080` shows the stream page.
2. Live: run without `--stdin` and type in `twitch.tv/popout/<channel>/chat` (works offline too).
3. A freeze: `saves/hang-report.txt` (empty = no freeze) shows where it stuck.
